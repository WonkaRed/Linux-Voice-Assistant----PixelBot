#!/usr/bin/env python3
"""
Nova — push-to-talk voice bridge to the Hermes agents on 10.0.0.75.

Press a key, speak, press again. Your words are transcribed locally (Whisper),
sent to an agent's Telegram bot as you (so the agent's live gateway handles it
in its canonical session), and the reply is spoken back here (Piper).

  F4 → Pixel Bot   (server `default` profile, cloud inference)
  F8 → Jailbreak   (server `jailbreak` profile, local qwen3.6-heretic-q8)

The desktop is a thin relay: STT in, agent text out, agent text in, TTS out.
All agent work happens in Hermes.
"""
import os
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEBUG = os.environ.get("NOVA_DEBUG", "").lower() in ("1", "true", "yes")

_SOUND_START = "/usr/share/sounds/freedesktop/stereo/device-added.oga"
_SOUND_STOP = "/usr/share/sounds/freedesktop/stereo/complete.oga"


class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; RED = "\033[91m"; GREEN = "\033[92m"
    YELLOW = "\033[93m"; BLUE = "\033[94m"; CYAN = "\033[96m"; GRAY = "\033[90m"


def log(msg, level="info"):
    color = {"info": C.BLUE, "ok": C.GREEN, "warn": C.YELLOW, "err": C.RED}.get(level, C.BLUE)
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}] {msg}{C.RESET}", flush=True)


def notify(title, msg):
    try:
        import subprocess
        subprocess.Popen(["notify-send", "-t", "2500", title, msg],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def play_sound(path):
    try:
        import subprocess
        subprocess.Popen(["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class VoiceBridge:
    def __init__(self, config):
        self.config = config
        self.stt = None
        self.tts = None
        self.audio = None
        self.relay = None
        self.socket_listener = None
        self.hotkeys = None

        self._running = False
        self._recording_agent = None   # None = idle, else agent currently recording
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ run
    def run(self, headless: bool = False):
        self._banner()
        self._load_models()
        self._connect_relay()
        self._start_listeners()
        if self.tts:
            self.tts.speak_async("Nova online.")
        self._running = True
        if headless:
            self._run_headless()
        else:
            self._input_loop()

    def _run_headless(self):
        """Service mode: no terminal — just keep the listeners alive."""
        import signal
        log("Running headless (service mode). Hotkeys via nova-toggle.", "ok")
        stop = threading.Event()

        def _on_signal(signum, _frame):
            log(f"Signal {signum} received — shutting down", "warn")
            stop.set()

        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
        stop.wait()
        self._running = False
        self._cleanup()

    def _load_models(self, with_stt: bool = True):
        log("Loading voice models...")
        try:
            from nova.voice.tts import TTSEngine
            self.tts = TTSEngine(voice_model=self.config.expanduser("voice.tts_voice"))

            if with_stt:
                from nova.voice.stt import STTEngine
                from nova.voice.audio import AudioCapture
                self.stt = STTEngine(
                    model_size=self.config.get("voice.stt_model", "large-v3-turbo"),
                    device=self.config.get("voice.stt_device", "cpu"),
                    compute_type=self.config.get("voice.stt_compute_type", "int8"),
                    cpu_threads=int(self.config.get("voice.stt_cpu_threads", 0)),
                )
                self.audio = AudioCapture()
            log("Voice models loaded", "ok")
            notify("Nova", "Voice ready")
        except Exception as e:
            log(f"Model loading failed: {e}", "err")
            log("Fix the model/GPU issue — voice won't work until then.", "warn")

    def _connect_relay(self):
        from nova.relay import TelegramRelay, RelayNotAuthorized
        from nova.config import telegram_credentials

        try:
            api_id, api_hash = telegram_credentials()
        except RuntimeError as e:
            log(str(e), "err")
            return

        self.relay = TelegramRelay(
            api_id=api_id,
            api_hash=api_hash,
            session=self.config.expanduser("telegram.session"),
            settle_s=float(self.config.get("relay.settle_s", 2.5)),
            reply_mode=self.config.get("relay.reply_mode", "last"),
        )
        try:
            self.relay.start()
            log("Connected to Telegram (relay ready)", "ok")
        except RelayNotAuthorized:
            log("Telegram session not authorized — run `nova login` first.", "err")
            self.relay = None
        except Exception as e:
            log(f"Relay connection failed: {e}", "err")
            self.relay = None

    def _start_listeners(self):
        from nova.hotkey import SocketCommandListener, HotkeyListener

        agents = self.config.agent_names
        self.socket_listener = SocketCommandListener(on_toggle=self._toggle, agents=agents)
        if self.socket_listener.start():
            hint = " | ".join(f"nova-toggle {a}" for a in agents)
            log(f"Socket ready: {hint}", "info")

        keymap = {}
        for agent in agents:
            key = self.config.get(f"keybinds.{agent}")
            if key:
                keymap[f"KEY_{str(key).upper()}"] = agent
        if keymap:
            self.hotkeys = HotkeyListener(keymap=keymap, on_toggle=self._toggle)
            self.hotkeys.start()

    # ------------------------------------------------------------------ recording
    def _toggle(self, agent):
        with self._lock:
            if agent == "__stop__":
                if self._recording_agent:
                    self._stop_and_process()
                return
            if self._recording_agent:
                # Already recording — stop and process against the ORIGINAL agent.
                self._stop_and_process()
            else:
                self._start_listening(agent)

    def _start_listening(self, agent):
        if not self.stt or not self.stt.is_ready:
            log("STT not ready — cannot record", "warn")
            notify("Nova", "Voice not ready")
            return
        try:
            self.config.agent(agent)
        except KeyError as e:
            log(str(e), "err")
            return

        if self.tts:
            self.tts.stop()  # barge-in: cut off any current speech
        if not self.audio:
            from nova.voice.audio import AudioCapture
            self.audio = AudioCapture()

        if self.audio.start():
            self._recording_agent = agent
            play_sound(_SOUND_START)
            log(f"Listening for {agent}... (press again to send)", "ok")
            notify("Nova", f"Listening → {agent}")

    def _stop_and_process(self):
        agent = self._recording_agent
        self._recording_agent = None
        play_sound(_SOUND_STOP)
        audio = self.audio.stop() if self.audio else None
        if audio is None:
            log("Recording too short", "warn")
            return
        threading.Thread(target=self._process, args=(agent, audio), daemon=True).start()

    def _process(self, agent, audio):
        try:
            start = time.time()
            text, _ = self.stt.transcribe(audio)
            if not text or not text.strip():
                log("No speech detected", "warn")
                self._speak("I didn't catch that.")
                return
            log(f"[{agent}] heard ({time.time()-start:.1f}s): {text}", "ok")

            if not self.relay or not self.relay.connected:
                self._speak("The relay isn't connected. Run nova login.")
                return

            bot = self.config.agent(agent)["bot"]
            timeout = float(self.config.agent(agent).get("reply_timeout_s", 180))
            log(f"[{agent}] asking Pixel Bot..." if agent == "pixelbot" else f"[{agent}] asking...", "info")
            notify("Nova", f"{agent} is thinking…")

            reply = self.relay.ask(bot, text, timeout=timeout)
            if reply and reply.strip():
                log(f"[{agent}] reply: {reply[:200]}", "ok")
                self._speak(reply)
            else:
                log(f"[{agent}] empty reply", "warn")
                self._speak("No answer came back.")
        except TimeoutError:
            log(f"[{agent}] timed out", "err")
            self._speak(f"{agent} took too long to answer.")
        except Exception as e:
            log(f"[{agent}] error: {e}", "err")
            self._speak("Something went wrong reaching the agent.")

    def _speak(self, text):
        if self.tts:
            self.tts.speak_async(text)

    # ------------------------------------------------------------------ terminal
    def _banner(self):
        agents = ", ".join(self.config.agent_names)
        print(f"""
{C.CYAN}{C.BOLD} N O V A {C.RESET}{C.GRAY}— voice bridge to Hermes{C.RESET}

{C.GRAY}Agents:{C.RESET} {agents}
{C.GRAY}Keys:{C.RESET}   F4 → pixelbot   F8 → jailbreak   (via COSMIC → nova-toggle)
{C.GRAY}Type:{C.RESET}   'pixelbot: <text>'  or  '/voice jailbreak'  |  /quit
{C.GRAY}{'─'*46}{C.RESET}
""", flush=True)

    def _input_loop(self):
        log("Ready.", "ok")
        while self._running:
            try:
                print(f"{C.GREEN}>{C.RESET} ", end="", flush=True)
                line = input().strip()
                if not line:
                    continue
                if line.startswith("/"):
                    self._handle_cmd(line)
                    continue
                # "agent: message" sends text straight to that agent (no voice).
                if ":" in line:
                    name, _, msg = line.partition(":")
                    name, msg = name.strip().lower(), msg.strip()
                    if name in self.config.agent_names and msg:
                        threading.Thread(target=self._send_text, args=(name, msg), daemon=True).start()
                        continue
                log("Use 'pixelbot: <text>' or '/voice <agent>' or /quit", "warn")
            except (KeyboardInterrupt, EOFError):
                print()
                break
        self._cleanup()

    def _send_text(self, agent, msg):
        if not self.relay or not self.relay.connected:
            log("Relay not connected — run nova login", "err")
            return
        try:
            bot = self.config.agent(agent)["bot"]
            timeout = float(self.config.agent(agent).get("reply_timeout_s", 180))
            log(f"[{agent}] sending...", "info")
            reply = self.relay.ask(bot, msg, timeout=timeout)
            log(f"[{agent}] reply: {reply[:200]}", "ok")
            self._speak(reply)
        except Exception as e:
            log(f"[{agent}] error: {e}", "err")

    def _handle_cmd(self, cmd):
        parts = cmd.lower().split()
        head = parts[0]
        if head in ("/quit", "/exit", "/q"):
            self._running = False
        elif head == "/voice" and len(parts) > 1 and parts[1] in self.config.agent_names:
            self._toggle(parts[1])
        elif head == "/stop":
            self._toggle("__stop__")
        elif head == "/help":
            log(f"/voice <{'|'.join(self.config.agent_names)}> | /stop | /quit")
        else:
            log(f"Unknown: {cmd}", "warn")

    def _cleanup(self):
        if self.tts:
            self.tts.shutdown() if hasattr(self.tts, "shutdown") else self.tts.stop()
        if self.socket_listener:
            self.socket_listener.stop()
        if self.hotkeys:
            self.hotkeys.stop()
        if self.relay:
            self.relay.stop()
        log("Goodbye.")
        os._exit(0)


# ---------------------------------------------------------------------- subcommands
def _interactive_login(config):
    """One-time Telethon user login (phone → code → optional 2FA)."""
    import asyncio
    from telethon import TelegramClient
    from nova.config import telegram_credentials

    api_id, api_hash = telegram_credentials()
    session = config.expanduser("telegram.session")
    os.makedirs(os.path.dirname(session), exist_ok=True)

    async def go():
        client = TelegramClient(session, api_id, api_hash)
        await client.start()  # prompts on stdin
        me = await client.get_me()
        print(f"Logged in as: {me.first_name} (@{me.username}) id={me.id}")
        await client.disconnect()

    asyncio.run(go())
    log("Login saved. You can now run `nova`.", "ok")


def _setup_list_bots(config):
    """List bot chats so you can fill agents.<name>.bot in config.yaml."""
    import asyncio
    from telethon import TelegramClient
    from nova.config import telegram_credentials

    api_id, api_hash = telegram_credentials()
    session = config.expanduser("telegram.session")

    async def go():
        client = TelegramClient(session, api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            print("Not authorized — run `nova login` first.")
            return
        print(f"{'id':>14}  {'@username':<24}  title")
        print("-" * 60)
        async for dialog in client.iter_dialogs():
            ent = dialog.entity
            if getattr(ent, "bot", False):
                uname = f"@{ent.username}" if getattr(ent, "username", None) else "-"
                print(f"{ent.id:>14}  {uname:<24}  {dialog.name}")
        await client.disconnect()

    asyncio.run(go())


def main():
    import argparse
    from nova.config import Config

    parser = argparse.ArgumentParser(description="Nova voice bridge to Hermes")
    parser.add_argument("--daemon", action="store_true",
                        help="Headless service mode (no terminal input loop)")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("login", help="One-time Telegram user login")
    sub.add_parser("setup", help="List bot chats to configure agents")
    ask = sub.add_parser("ask", help="One-shot: send text to an agent and print+speak the reply")
    ask.add_argument("agent")
    ask.add_argument("message", nargs="+")
    args = parser.parse_args()

    config = Config.load()

    if args.cmd == "login":
        _interactive_login(config)
        return
    if args.cmd == "setup":
        _setup_list_bots(config)
        return
    if args.cmd == "ask":
        bridge = VoiceBridge(config)
        bridge._connect_relay()
        if not bridge.relay:
            sys.exit(1)
        bridge._load_models(with_stt=False)  # text-only path needs just TTS
        bridge._send_text(args.agent, " ".join(args.message))
        time.sleep(0.5)
        return

    # Headless when asked, or when there's no terminal (i.e. run as a service).
    headless = args.daemon or not sys.stdin.isatty()
    VoiceBridge(config).run(headless=headless)


if __name__ == "__main__":
    main()
