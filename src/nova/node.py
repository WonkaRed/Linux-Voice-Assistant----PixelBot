#!/usr/bin/env python3
"""
Nova GPU Node — Desktop voice interface connected to Nova Server.

Manages:
- STT/TTS model lifecycle (load/unload)
- Audio capture (push-to-talk F4)
- WebSocket connection to Nova Server
- VRAM-submissive model management
- Local tool execution on behalf of server
"""
import gc
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEBUG = os.environ.get('NOVA_DEBUG', '').lower() in ('1', 'true', 'yes')


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
    except Exception:
        pass


# ============================================================================
# NODE
# ============================================================================

class NovaNode:
    """
    Desktop GPU node for Nova voice assistant.

    Connects to Nova Server via WebSocket.
    Manages STT/TTS/VRAM locally, executes tools on server request.
    """

    def __init__(self, server_url: str, auth_token: str,
                 auto_load_models: bool = True):
        self.server_url = server_url
        self.auth_token = auth_token
        self.auto_load_models = auto_load_models

        self.stt = None
        self.tts = None
        self.audio = None
        self.connection = None
        self.vram_monitor = None
        self.hotkeys = None
        self.socket_listener = None
        self.tools = {}

        self._running = False
        self._models_loaded = False
        self._listening = False

    def run(self):
        """Run the GPU node."""
        self._print_banner()

        # Load tools (always available)
        self._load_tools()

        # Load voice models
        if self.auto_load_models:
            self._load_models()

        # Connect to server
        self._connect_to_server()

        # Start VRAM monitor
        self._start_vram_monitor()

        # Start hotkey listeners
        self._start_hotkeys()

        # Welcome
        if self.tts:
            self._speak("Nova online. Connected to server.")

        # Main loop
        self._running = True
        self._input_loop()

    def _load_tools(self):
        """Load local tools."""
        try:
            from nova.tools import SystemStatsTool, ClipboardTool, TimerTool, NotesTool
            self.tools = {
                "system_stats": SystemStatsTool(),
                "clipboard": ClipboardTool(),
                "timer": TimerTool(),
                "notes": NotesTool(),
            }
            log(f"Tools loaded: {list(self.tools.keys())}", "ok")
        except Exception as e:
            log(f"Tool loading failed: {e}", "err")

    def _load_models(self):
        """Load STT and TTS models."""
        log("Loading voice models...")

        try:
            from nova.voice.stt import STTEngine
            from nova.voice.tts import TTSEngine
            from nova.config import get_config

            config = get_config()
            stt_model = config.get("voice.stt_model", "large-v3")

            self.stt = STTEngine(model_size=stt_model)
            self.tts = TTSEngine()

            from nova.voice.audio import AudioCapture
            self.audio = AudioCapture()

            self._models_loaded = True
            log(f"Voice models loaded (STT: {stt_model})", "ok")
            notify("Nova", "Voice models loaded")

        except Exception as e:
            log(f"Model loading failed: {e}", "err")
            log("Node will run without voice — text-only mode", "warn")

    def _unload_models(self):
        """Unload STT/TTS models to free VRAM."""
        if not self._models_loaded:
            return

        log("Unloading voice models (VRAM pressure)...")

        # Don't unload during active recording
        if self._listening:
            log("Active recording — deferring unload", "warn")
            return

        if self.stt and hasattr(self.stt, 'model') and self.stt.model:
            del self.stt.model
            self.stt.model = None

        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        self._models_loaded = False
        log("Voice models unloaded — VRAM freed", "ok")
        notify("Nova", "Voice paused — GPU in use")

        # Notify server
        if self.connection and self.connection.connected:
            self._send_vram_status()

    def _reload_models(self):
        """Reload STT/TTS models after VRAM pressure relieved."""
        if self._models_loaded:
            return

        log("Reloading voice models...")
        self._load_models()

        if self.connection and self.connection.connected:
            self._send_vram_status()

    def _connect_to_server(self):
        """Establish WebSocket connection to Nova Server."""
        from nova.connection import ServerConnection

        self.connection = ServerConnection(
            url=self.server_url,
            auth_token=self.auth_token,
            on_message=self._handle_server_message,
            on_connected=self._on_server_connected,
            on_disconnected=self._on_server_disconnected,
        )
        self.connection.start()
        log(f"Connecting to server: {self.server_url}", "info")

    def _on_server_connected(self):
        """Called when connected to server."""
        log("Connected to Nova Server", "ok")
        notify("Nova", "Server connected")
        self._send_vram_status()

    def _on_server_disconnected(self):
        """Called when disconnected from server."""
        log("Disconnected from server (will reconnect)", "warn")

    def _handle_server_message(self, data: dict):
        """Handle incoming message from server."""
        msg_type = data.get("type")

        if msg_type == "speak":
            text = data.get("text", "")
            if text:
                log(f"Speaking: {text[:60]}...")
                self._speak(text)

        elif msg_type == "tool_request":
            request_id = data.get("request_id")
            tool_name = data.get("tool")
            params = data.get("params", {})
            self._execute_tool(request_id, tool_name, params)

        elif msg_type == "model_command":
            action = data.get("action")
            self._handle_model_command(action)

        elif msg_type == "error":
            log(f"Server error: {data.get('message')}", "err")

    def _execute_tool(self, request_id: str, tool_name: str, params: dict):
        """Execute a local tool and send result to server."""
        def _run():
            tool = self.tools.get(tool_name)
            if not tool:
                result = f"ERROR: Unknown tool '{tool_name}'"
            else:
                try:
                    result = tool.execute(**params)
                except Exception as e:
                    result = f"ERROR: {tool_name} failed: {e}"

            if self.connection and self.connection.connected:
                self.connection.send({
                    "type": "tool_result",
                    "request_id": request_id,
                    "result": result,
                })

        threading.Thread(target=_run, daemon=True).start()

    def _handle_model_command(self, action: str):
        """Handle model management command from server."""
        if action == "unload_stt":
            self._unload_models()
        elif action == "load_stt":
            self._reload_models()
        elif action == "unload_all":
            self._unload_models()
        else:
            log(f"Unknown model command: {action}", "warn")

    def _speak(self, text: str):
        """Speak text via TTS (non-blocking)."""
        if not self.tts:
            return

        def _do_speak():
            try:
                self.tts.speak(text)
            except Exception as e:
                log(f"TTS error: {e}", "err")

        threading.Thread(target=_do_speak, daemon=True).start()

    def _start_vram_monitor(self):
        """Start VRAM monitoring."""
        try:
            from nova.vram import VRAMMonitor
            from nova.config import get_config

            config = get_config()
            vram_config = config.get_section("vram") if hasattr(config, 'get_section') else {}

            self.vram_monitor = VRAMMonitor(
                unload_threshold_gb=vram_config.get("unload_threshold_gb", 4.0),
                reload_threshold_gb=vram_config.get("reload_threshold_gb", 8.0),
                poll_interval_s=vram_config.get("poll_interval_s", 1.0),
                hysteresis_s=vram_config.get("hysteresis_s", 10.0),
                monitored_processes=vram_config.get("monitored_processes",
                    ["comfyui", "python", "blender", "resolve"]),
                on_pressure_detected=self._unload_models,
                on_pressure_relieved=self._reload_models,
            )
            self.vram_monitor.start()
            log("VRAM monitor started", "ok")

        except Exception as e:
            log(f"VRAM monitor failed: {e}", "warn")

    def _send_vram_status(self):
        """Send current VRAM status to server."""
        if not self.vram_monitor or not self.vram_monitor.is_available:
            return

        status = self.vram_monitor.get_status()
        if not status:
            return

        models_loaded = []
        if self._models_loaded:
            if self.stt and self.stt.is_ready:
                models_loaded.append("stt_large_v3")
            if self.tts and self.tts.is_ready:
                models_loaded.append("tts_piper_ryan")

        self.connection.send({
            "type": "vram_status",
            "free_gb": round(status.free_gb, 2),
            "used_gb": round(status.used_gb, 2),
            "total_gb": round(status.total_gb, 2),
            "models_loaded": models_loaded,
            "external_processes": [
                {"name": p["name"], "pid": p["pid"], "vram_gb": round(p["vram_mb"] / 1000, 2)}
                for p in status.processes
                if p["pid"] != os.getpid()
            ],
        })

    def _start_hotkeys(self):
        """Start hotkey and socket listeners."""
        from nova.hotkey import HotkeyListener, SocketCommandListener

        # Socket listener (PRIMARY — works on Wayland)
        self.socket_listener = SocketCommandListener(
            on_toggle_voice=self._toggle_voice,
            on_toggle_agent=lambda: None,  # No local agent in node mode
        )
        if self.socket_listener.start():
            log(f"Socket: echo 'toggle' | nc -U /tmp/nova-voice.sock", "info")

        # Evdev hotkeys (FALLBACK)
        self.hotkeys = HotkeyListener(
            on_f4=self._toggle_voice,
            on_super_f4=lambda: None,
        )
        if not self.hotkeys.start():
            log("Evdev hotkeys not available (normal on Wayland)", "info")

    def _toggle_voice(self):
        """Toggle voice recording."""
        if self._listening:
            self._stop_listening()
        else:
            self._start_listening()

    def _start_listening(self):
        """Start voice recording."""
        if self._listening:
            return

        if not self._models_loaded:
            log("Voice models not loaded — can't record", "warn")
            notify("Nova", "Voice paused — GPU in use")
            return

        if not self.audio:
            from nova.voice.audio import AudioCapture
            self.audio = AudioCapture()

        if self.vram_monitor:
            from nova.vram import VRAMState
            self.vram_monitor.state = VRAMState.ACTIVE

        if self.audio.start():
            self._listening = True
            log("Listening... (F4 or /stop to finish)", "ok")
            notify("Nova", "Listening...")

    def _stop_listening(self):
        """Stop recording and process."""
        if not self._listening:
            return

        self._listening = False

        if self.vram_monitor:
            from nova.vram import VRAMState
            self.vram_monitor.state = VRAMState.LOADED

        audio = self.audio.stop() if self.audio else None
        if audio is None:
            log("Recording too short", "warn")
            return

        log("Transcribing...")

        try:
            start = time.time()
            text, info = self.stt.transcribe(audio)
            stt_latency = time.time() - start

            if not text or not text.strip():
                log("No speech detected", "warn")
                self._speak("I didn't catch that.")
                return

            log(f"Transcribed ({stt_latency:.1f}s): {text}")

            # Send to server
            if self.connection and self.connection.connected:
                self.connection.send({
                    "type": "transcription",
                    "text": text,
                    "audio_duration_s": len(audio) / 16000,
                    "stt_latency_s": round(stt_latency, 2),
                })
            else:
                # Degraded mode — no server, try to handle locally
                log("Server offline — degraded mode", "warn")
                self._handle_degraded(text)

        except Exception as e:
            log(f"Transcription error: {e}", "err")

    def _handle_degraded(self, text: str):
        """Handle a query locally when server is unreachable."""
        # Try to match a local tool
        import re
        msg_lower = text.lower()

        tool_patterns = {
            "system_stats": r"\b(gpu|cpu|ram|memory|disk|temp|vram|system\s*stats)\b",
            "time": r"\bwhat\s+(time|day)\s+is\s+it\b",
        }

        for tool_name, pattern in tool_patterns.items():
            if re.search(pattern, msg_lower, re.I):
                if tool_name == "time":
                    now = datetime.now()
                    response = now.strftime("It's %I:%M %p.") if "time" in msg_lower else now.strftime("It's %A, %B %d.")
                    self._speak(response)
                    return
                elif tool_name in self.tools:
                    result = self.tools[tool_name].execute(stat_type="overview")
                    self._speak(result)
                    return

        self._speak("I can't reach the server right now. Try again in a moment.")

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
{C.GRAY}Mode: GPU Node (connected to Nova Server){C.RESET}
{C.GRAY}Server: {self.server_url}{C.RESET}
{C.GRAY}Local tools: system_stats, clipboard, timer, notes{C.RESET}

{C.GRAY}Commands:{C.RESET}
  Type message + Enter = send to server
  /voice = start listening    /stop = stop listening
  /vram  = VRAM status        /models = reload models
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

                if line.startswith('/'):
                    self._handle_cmd(line.lower())
                else:
                    # Send text to server as transcription
                    if self.connection and self.connection.connected:
                        self.connection.send({
                            "type": "transcription",
                            "text": line,
                            "audio_duration_s": 0,
                            "stt_latency_s": 0,
                        })
                        log("Sent to server...")
                    else:
                        log("Server not connected", "warn")
                        self._handle_degraded(line)

            except KeyboardInterrupt:
                print()
                log("Interrupted")
                break
            except EOFError:
                break

        self._cleanup()

    def _handle_cmd(self, cmd: str):
        """Handle command."""
        if cmd in ('/quit', '/exit', '/q'):
            self._running = False
        elif cmd == '/voice':
            self._toggle_voice()
        elif cmd == '/stop':
            self._stop_listening()
        elif cmd == '/vram':
            self._show_vram()
        elif cmd == '/models':
            if self._models_loaded:
                log("Models already loaded", "info")
            else:
                self._reload_models()
        elif cmd == '/help':
            log("Commands: /voice /stop /vram /models /quit")
        else:
            log(f"Unknown: {cmd}. Try /help", "warn")

    def _show_vram(self):
        """Show current VRAM status."""
        if not self.vram_monitor or not self.vram_monitor.is_available:
            log("VRAM monitor not available", "warn")
            return

        status = self.vram_monitor.get_status()
        if not status:
            log("Could not read VRAM status", "warn")
            return

        log(f"VRAM: {status.free_gb:.1f}GB free / {status.total_gb:.1f}GB total", "info")
        log(f"State: {self.vram_monitor.state.value}", "info")
        for p in status.processes:
            log(f"  {p['name']} (PID {p['pid']}): {p['vram_mb']:.0f}MB", "info")

    def _cleanup(self):
        """Clean shutdown."""
        if self.hotkeys:
            self.hotkeys.stop()
        if self.socket_listener:
            self.socket_listener.stop()
        if self.vram_monitor:
            self.vram_monitor.stop()
        if self.connection:
            self.connection.stop()
        log("Goodbye!")
        os._exit(0)


# ============================================================================
# ENTRY
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Nova GPU Node")
    parser.add_argument("--standalone", action="store_true",
                        help="Run in standalone mode (old runner.py behavior)")
    parser.add_argument("--no-models", action="store_true",
                        help="Don't auto-load STT/TTS models")
    parser.add_argument("--server-url", default=None,
                        help="Nova Server WebSocket URL")
    parser.add_argument("--ssh-host", default=None,
                        help="SSH host (standalone mode only)")
    parser.add_argument("-q", "--query", default=None,
                        help="Single-shot text query (standalone mode)")
    args = parser.parse_args()

    if args.standalone or args.query:
        # Fall back to old runner.py behavior
        from nova.runner import main as runner_main
        sys.argv = [sys.argv[0]]
        if args.query:
            sys.argv.extend(['-q', args.query])
        if args.ssh_host:
            sys.argv.extend(['--ssh-host', args.ssh_host])
        if args.no_models:
            sys.argv.append('--no-load')
        runner_main()
        return

    # Node mode (default)
    from nova.config import get_config
    config = get_config()

    server_config = config.get_section("server") if hasattr(config, 'get_section') else {}
    server_url = args.server_url or server_config.get("url", "ws://10.0.0.75:9600")
    auth_token = server_config.get("auth_token", "")

    if not auth_token:
        log("No auth_token in config! Set server.auth_token in ~/.nova/config.yaml", "err")
        sys.exit(1)

    node = NovaNode(
        server_url=server_url,
        auth_token=auth_token,
        auto_load_models=not args.no_models,
    )
    node.run()


if __name__ == "__main__":
    main()
