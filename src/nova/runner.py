#!/usr/bin/env python3
"""
Nova Voice Assistant. Local tools + Pixel Bot intelligence.
Piper TTS (ryan-high). Faster-whisper large-v3 STT.
"""
import sys
import os
import time
import threading
import socket
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Debug mode - set NOVA_DEBUG=1 to enable verbose logging
DEBUG = os.environ.get('NOVA_DEBUG', '').lower() in ('1', 'true', 'yes')

# Socket path for IPC (Wayland-compatible hotkey alternative)
SOCKET_PATH = os.environ.get('NOVA_SOCKET', '/tmp/nova-voice.sock')


# ============================================================================
# COLORS
# ============================================================================

class C:
    """ANSI colors."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


def log(msg, level="info"):
    """Print timestamped log message."""
    colors = {"info": C.BLUE, "ok": C.GREEN, "warn": C.YELLOW, "err": C.RED}
    color = colors.get(level, C.BLUE)
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}] {msg}{C.RESET}", flush=True)


def notify(title, msg):
    """Desktop notification."""
    try:
        import subprocess
        subprocess.Popen(["notify-send", "-t", "2000", title, msg],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass


# ============================================================================
# AGENT
# ============================================================================

class NovaAgent:
    """Agent wrapper for Pixel Bot integration."""

    def __init__(self, ssh_host=None):
        self._ssh_host = ssh_host  # Override from CLI
        self._agent = None
        self._loaded = False

    def load(self):
        """Load agent with Pixel Bot connection."""
        if self._loaded:
            log("Agent already loaded", "warn")
            return True

        log("Loading agent...")
        try:
            from nova.agent import Agent
            from nova.config import get_config

            config = get_config()
            pb = config.pixelbot

            ssh_host = self._ssh_host or pb.get("ssh_host", "pixel-labs-server")

            self._agent = Agent(
                ssh_host=ssh_host,
                agent_name=pb.get("agent_name", "main"),
                session_id=pb.get("session_id", "nova-desktop"),
                timeout=pb.get("timeout", 15),
                max_retries=pb.get("max_retries", 1),
                retry_delay=pb.get("retry_delay", 2.0),
            )

            log("Checking Pixel Bot connectivity...")
            if not self._agent.is_ready():
                log(f"Pixel Bot unreachable via {ssh_host}!", "err")
                log("Check: ssh pixel-labs-server 'echo pong'", "warn")
                return False

            self._loaded = True
            log(f"Agent loaded: Pixel Bot via {ssh_host}", "ok")
            notify("Nova", "Pixel Bot connected")
            return True
        except Exception as e:
            log(f"Load failed: {e}", "err")
            return False

    def unload(self):
        """Unload agent."""
        if not self._loaded:
            log("Agent not loaded", "warn")
            return
        self._agent = None
        self._loaded = False
        import gc; gc.collect()
        log("Agent unloaded", "ok")
        notify("Nova", "Agent unloaded")

    def toggle(self):
        """Toggle load state."""
        if self._loaded:
            self.unload()
        else:
            self.load()

    def chat(self, msg):
        """Chat with agent."""
        if not self._loaded:
            if not self.load():
                return "Agent not available."

        print(f"\n{C.BOLD}You:{C.RESET} {msg}", flush=True)

        try:
            start = time.time()
            log("Thinking...")
            response = self._agent.chat(msg)
            elapsed = time.time() - start

            print(f"\n{C.GREEN}{C.BOLD}Nova:{C.RESET}", flush=True)
            for line in response.split('\n'):
                print(f"  {line}", flush=True)
            log(f"Done ({elapsed:.1f}s)", "ok")
            return response

        except Exception as e:
            log(f"Chat error: {e}", "err")
            return "Error processing request."

    @property
    def is_loaded(self):
        return self._loaded


# ============================================================================
# VOICE
# ============================================================================

class NovaVoice:
    """Voice interface."""

    def __init__(self, agent):
        self.agent = agent
        self.stt = None
        self.tts = None
        self._loaded = False
        self._listening = False
        self._audio_buffer = []
        self._pa = None
        self._stream = None

    def load(self):
        """Load voice components."""
        if self._loaded:
            return True

        log("Loading voice...")
        try:
            from nova.voice.stt import STTEngine
            from nova.voice.tts import TTSEngine
            from nova.config import get_config

            config = get_config()
            stt_model = config.get("voice.stt_model", "large-v3")

            self.stt = STTEngine(model_size=stt_model)
            self.tts = TTSEngine()
            self._loaded = True
            log(f"Voice ready (STT: {stt_model})", "ok")
            return True
        except Exception as e:
            log(f"Voice load failed: {e}", "err")
            return False

    def speak(self, text):
        """Speak text (non-blocking)."""
        if not self.tts:
            return
        # Run TTS in background thread
        def _speak():
            try:
                self.tts.speak(text)
            except Exception as e:
                log(f"TTS error: {e}", "err")
        threading.Thread(target=_speak, daemon=True).start()

    def start_listening(self):
        """Start recording."""
        if DEBUG:
            log(f"DEBUG: start_listening called, _listening={self._listening}, _loaded={self._loaded}")
        if self._listening:
            if DEBUG:
                log("DEBUG: Already listening, returning")
            return

        if not self._loaded:
            if DEBUG:
                log("DEBUG: Voice not loaded, loading now")
            if not self.load():
                if DEBUG:
                    log("DEBUG: Voice load failed")
                return

        try:
            import pyaudio
            import numpy as np
            if DEBUG:
                log("DEBUG: pyaudio imported successfully")

            # Suppress ALSA/JACK warnings during PyAudio init
            import os
            import sys
            devnull = os.open(os.devnull, os.O_WRONLY)
            old_stderr = os.dup(2)
            os.dup2(devnull, 2)
            try:
                self._pa = pyaudio.PyAudio()
            finally:
                os.dup2(old_stderr, 2)
                os.close(devnull)
                os.close(old_stderr)
            self._audio_buffer = []
            if DEBUG:
                log("DEBUG: PyAudio initialized")

            def callback(in_data, frame_count, time_info, status):
                import numpy as np
                if self._listening:
                    self._audio_buffer.append(np.frombuffer(in_data, dtype=np.float32))
                return (None, pyaudio.paContinue)

            self._stream = self._pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024,
                stream_callback=callback
            )
            self._listening = True
            self._stream.start_stream()
            if DEBUG:
                log("DEBUG: Stream started successfully")
            log("Listening... (F4 or /stop to finish)", "ok")
            notify("Nova", "Listening...")
        except Exception as e:
            log(f"Mic error: {e}", "err")
            if DEBUG:
                import traceback
                log(f"DEBUG: Full traceback: {traceback.format_exc()}", "err")

    def stop_listening(self):
        """Stop recording and process."""
        if not self._listening:
            log("Not listening", "warn")
            return

        import numpy as np
        self._listening = False

        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        if self._pa:
            self._pa.terminate()

        audio = np.concatenate(self._audio_buffer) if self._audio_buffer else np.array([])
        self._audio_buffer = []

        if len(audio) < 8000:  # < 0.5s
            log("Recording too short", "warn")
            return

        log(f"Captured {len(audio)/16000:.1f}s audio")
        log("Transcribing...")

        try:
            text, _ = self.stt.transcribe(audio)
            if not text or not text.strip():
                log("No speech detected", "warn")
                self.speak("I didn't catch that.")
                return

            response = self.agent.chat(text)
            self.speak(response)
        except Exception as e:
            log(f"Transcribe error: {e}", "err")


# ============================================================================
# HOTKEYS (EVDEV)
# ============================================================================

class HotkeyListener:
    """Hotkey listener using evdev."""

    def __init__(self, on_f4, on_super_f4):
        self.on_f4 = on_f4
        self.on_super_f4 = on_super_f4
        self._running = False
        self._thread = None
        self._device = None

    def start(self):
        """Start listener."""
        try:
            import evdev
            from evdev import ecodes

            # Find REAL keyboard - prioritize actual keyboard over mouse's keyboard interface
            candidates = []
            for path in evdev.list_devices():
                try:
                    dev = evdev.InputDevice(path)
                    caps = dev.capabilities().get(ecodes.EV_KEY, [])
                    has_f4 = ecodes.KEY_F4 in caps
                    has_a = ecodes.KEY_A in caps
                    name_lower = dev.name.lower()

                    if not (has_f4 and has_a):
                        continue

                    if "viper" in name_lower or "mouse" in name_lower:
                        if DEBUG:
                            log(f"Skipping mouse interface: {dev.name}", "info")
                        continue

                    score = 0
                    if "ornata" in name_lower:
                        score += 100
                    if "keyboard" in name_lower:
                        score += 10

                    if score > 0:
                        candidates.append((score, dev))
                        if DEBUG:
                            log(f"Candidate keyboard: {dev.name} (score={score})", "info")
                except:
                    pass

            best_device = None
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_device = candidates[0][1]
                log(f"Selected keyboard: {best_device.name}", "ok")

            if not best_device:
                log("No keyboard found for hotkeys", "warn")
                return False

            self._device = best_device
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return True

        except PermissionError:
            log("No permission for hotkeys. Run: sudo usermod -aG input $USER", "err")
            return False
        except Exception as e:
            log(f"Hotkey init failed: {e}", "err")
            return False

    def _loop(self):
        """Event loop."""
        import select
        from evdev import ecodes
        super_pressed = False

        try:
            while self._running:
                r, w, x = select.select([self._device.fd], [], [], 0.5)
                if not r:
                    continue

                for event in self._device.read():
                    if not self._running:
                        return
                    if event.type != ecodes.EV_KEY:
                        continue

                    key = event.code
                    pressed = event.value == 1

                    if key in (ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA):
                        super_pressed = pressed
                        continue

                    if key == ecodes.KEY_F4 and pressed:
                        if super_pressed:
                            if DEBUG:
                                log("DEBUG: Super+F4 pressed - calling on_super_f4()")
                            self.on_super_f4()
                        else:
                            if DEBUG:
                                log("DEBUG: F4 pressed - calling on_f4()")
                            self.on_f4()
        except Exception as e:
            if self._running:
                log(f"Hotkey error: {e}", "err")

    def stop(self):
        """Stop listener."""
        self._running = False
        if self._device:
            try:
                self._device.close()
            except:
                pass


# ============================================================================
# SOCKET COMMAND LISTENER (Wayland-compatible)
# ============================================================================

class SocketCommandListener:
    """
    Listen for commands via Unix socket.

    Commands:
    - "toggle" or "voice" - Toggle voice recording
    - "agent" - Toggle agent load/unload
    - "stop" - Stop listening
    - "status" - Return current status
    """

    def __init__(self, on_toggle_voice, on_toggle_agent):
        self.on_toggle_voice = on_toggle_voice
        self.on_toggle_agent = on_toggle_agent
        self._running = False
        self._thread = None
        self._socket = None
        self._socket_path = SOCKET_PATH

    def start(self):
        """Start socket listener."""
        try:
            if os.path.exists(self._socket_path):
                os.unlink(self._socket_path)

            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.bind(self._socket_path)
            self._socket.listen(5)
            self._socket.settimeout(0.5)

            os.chmod(self._socket_path, 0o666)

            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

            log(f"Socket listener: {self._socket_path}", "ok")
            return True

        except Exception as e:
            log(f"Socket listener failed: {e}", "err")
            return False

    def _loop(self):
        """Listen for commands."""
        while self._running:
            try:
                conn, _ = self._socket.accept()
                conn.settimeout(1.0)

                try:
                    data = conn.recv(256).decode('utf-8').strip().lower()

                    if data in ('toggle', 'voice', 'f4'):
                        log("Socket: toggle voice")
                        self.on_toggle_voice()
                        conn.sendall(b"OK: voice toggled\n")

                    elif data in ('agent', 'load', 'super+f4'):
                        log("Socket: toggle agent")
                        self.on_toggle_agent()
                        conn.sendall(b"OK: agent toggled\n")

                    elif data == 'stop':
                        log("Socket: stop listening")
                        conn.sendall(b"OK: stop\n")

                    elif data == 'status':
                        conn.sendall(b"OK: nova running\n")

                    elif data == 'ping':
                        conn.sendall(b"pong\n")

                    else:
                        conn.sendall(f"ERROR: unknown command '{data}'\n".encode())

                except socket.timeout:
                    pass
                finally:
                    conn.close()

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    if DEBUG:
                        log(f"Socket error: {e}", "warn")

    def stop(self):
        """Stop listener."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        if os.path.exists(self._socket_path):
            try:
                os.unlink(self._socket_path)
            except:
                pass


# ============================================================================
# MAIN RUNNER
# ============================================================================

class Nova:
    """Main Nova runner."""

    def __init__(self, ssh_host=None, auto_load=True):
        self.agent = NovaAgent(ssh_host=ssh_host)
        self.voice = NovaVoice(self.agent)
        self.hotkeys = None
        self.socket_listener = None
        self._running = False
        self._auto_load = auto_load

    def run(self):
        """Run Nova."""
        self._print_banner()

        # Load voice
        if not self.voice.load():
            log("Voice failed to load", "err")
            return

        # Auto-load agent
        if self._auto_load:
            self.agent.load()

        # Setup socket listener (PRIMARY - works on Wayland)
        self.socket_listener = SocketCommandListener(
            on_toggle_voice=self._toggle_voice,
            on_toggle_agent=self.agent.toggle
        )
        if self.socket_listener.start():
            log(f"Use: echo 'toggle' | nc -U {SOCKET_PATH}", "info")
        else:
            log("Socket listener failed", "warn")

        # Setup evdev hotkeys (FALLBACK - only works on X11)
        self.hotkeys = HotkeyListener(
            on_f4=self._toggle_voice,
            on_super_f4=self.agent.toggle
        )
        if not self.hotkeys.start():
            log("Evdev hotkeys not available (normal on Wayland)", "info")

        # Welcome
        self.voice.speak("Nova online. Pixel Bot connected.")

        # Main loop
        self._running = True
        self._input_loop()

    def _print_banner(self):
        """Print banner."""
        print(f"""
{C.CYAN}{C.BOLD}
 ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗
 ████╗  ██║██╔═══██╗██║   ██║██╔══██╗
 ██╔██╗ ██║██║   ██║██║   ██║███████║
 ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║
 ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║
 ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝
{C.RESET}
{C.GRAY}Intelligence: Pixel Bot (Claude Sonnet @ 10.0.0.75){C.RESET}
{C.GRAY}Local tools: system_stats, clipboard, timer, notes{C.RESET}

{C.GRAY}Commands:{C.RESET}
  Type message + Enter = chat
  /voice = start listening    /stop = stop listening
  /load  = load agent         /unload = unload agent
  /quit  = exit

{C.GRAY}Hotkey (Wayland):{C.RESET} Bind F4 to: nova-toggle
{C.GRAY}{'─'*40}{C.RESET}
""", flush=True)

    def _input_loop(self):
        """Main input loop."""
        log("Ready! Type a message or command.", "ok")

        while self._running:
            try:
                print(f"{C.GREEN}>{C.RESET} ", end="", flush=True)
                line = input().strip()

                if not line:
                    continue

                # Commands
                if line.startswith('/'):
                    self._handle_cmd(line.lower())
                else:
                    # Chat
                    response = self.agent.chat(line)
                    self.voice.speak(response)

            except KeyboardInterrupt:
                print()
                log("Interrupted")
                break
            except EOFError:
                break

        self._cleanup()

    def _handle_cmd(self, cmd):
        """Handle command."""
        if cmd in ('/quit', '/exit', '/q'):
            self._running = False
        elif cmd == '/load':
            self.agent.load()
        elif cmd == '/unload':
            self.agent.unload()
        elif cmd == '/voice':
            self._toggle_voice()
        elif cmd == '/stop':
            self.voice.stop_listening()
        elif cmd == '/clear':
            if self.agent._agent:
                self.agent._agent.clear_history()
            log("History cleared", "ok")
        elif cmd == '/help':
            log("Commands: /voice /stop /load /unload /clear /quit")
        else:
            log(f"Unknown: {cmd}. Try /help", "warn")

    def _toggle_voice(self):
        """Toggle voice listening."""
        if DEBUG:
            log(f"DEBUG: _toggle_voice called, currently listening={self.voice._listening}")
        if self.voice._listening:
            if DEBUG:
                log("DEBUG: Stopping listening")
            self.voice.stop_listening()
        else:
            if DEBUG:
                log("DEBUG: Starting listening")
            self.voice.start_listening()

    def _cleanup(self):
        """Cleanup."""
        if self.hotkeys:
            self.hotkeys.stop()
        if self.socket_listener:
            self.socket_listener.stop()
        log("Goodbye!")
        # Force clean exit to avoid thread crash
        import os
        os._exit(0)


# ============================================================================
# ENTRY
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Nova Voice Assistant")
    parser.add_argument("--no-load", action="store_true", help="Don't auto-load agent")
    parser.add_argument("--ssh-host", default=None, help="SSH host alias override")
    parser.add_argument("-q", "--query", default=None, help="Single-shot text query (print response and exit)")
    args = parser.parse_args()

    if args.query:
        # Single-shot mode: send query, print response, exit
        from nova.agent import Agent
        from nova.config import get_config
        config = get_config()
        pb = config.pixelbot
        agent = Agent(
            ssh_host=args.ssh_host or pb.get("ssh_host", "pixel-labs-server"),
            agent_name=pb.get("agent_name", "main"),
            session_id=pb.get("session_id", "nova-desktop"),
            timeout=pb.get("timeout", 15),
            max_retries=pb.get("max_retries", 1),
            retry_delay=pb.get("retry_delay", 2.0),
        )
        print(agent.chat(args.query))
        return

    nova = Nova(ssh_host=args.ssh_host, auto_load=not args.no_load)
    nova.run()


if __name__ == "__main__":
    main()
