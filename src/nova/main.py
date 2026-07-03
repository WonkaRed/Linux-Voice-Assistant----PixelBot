#!/usr/bin/env python3
"""
Nova — push-to-talk voice bridge to the Hermes agents on 10.0.0.75.

Press a key, speak (as long as you like — up to ~12 min), press again. Your
words are transcribed locally (Whisper), sent to an agent's Telegram bot as you
(so the agent's live gateway handles it in its canonical session), and the reply
is spoken back here (Piper).

  F4 → Pixel Bot   (server `default` profile, cloud inference)
  F8 → Jailbreak   (server `jailbreak` profile, local qwen3.6-heretic-q8)

Design notes:
- Long takes are transcribed in the background *while* you talk (see
  streaming.py), so stopping returns the full transcript almost immediately.
- TTS never plays while the mic is recording — that killed an echo loop where
  the agent's spoken reply was picked up and re-sent as your next message.
"""
import os
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEBUG = os.environ.get("NOVA_DEBUG", "").lower() in ("1", "true", "yes")

_ASSETS = Path(__file__).resolve().parents[2] / "assets" / "sounds"


def _sound(name, fallback):
    p = _ASSETS / name
    return str(p) if p.exists() else fallback


_SOUND_START = _sound("start.wav", "/usr/share/sounds/freedesktop/stereo/device-added.oga")
_SOUND_STOP = _sound("stop.wav", "/usr/share/sounds/freedesktop/stereo/complete.oga")


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
        self.tts_engines = {}   # agent name -> TTSEngine (own voice per agent)
        self.audio = None
        self.relay = None
        self.socket_listener = None
        self.hotkeys = None
        self.streamer = None

        self._running = False
        self._recording_agent = None      # None = idle, else agent being recorded
        self._lock = threading.Lock()     # guards toggle state transitions
        self._stt_lock = threading.Lock() # serialises model access (poll vs finish)
        self._rec_active = threading.Event()
        self._poll_thread = None
        self._rec_started = 0.0

        # Speech is queued (agent, text) and only ever played when the mic is
        # idle (anti-echo); each agent speaks in its own configured voice.
        self._speech_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._speech_thread = None
        self._speech_epoch = 0   # bumped on barge-in to drop in-flight speech

        self._last_toggle = 0.0
        self._debounce_s = 0.4
        self._max_record_s = float(config.get("voice.max_record_s", 720))  # 12 min safety cap
        self._chunk_s = float(config.get("voice.stream_chunk_s", 15))

    # ------------------------------------------------------------------ run
    def run(self, headless: bool = False):
        self._banner()
        self._load_models()
        self._connect_relay()
        self._running = True            # must precede the speech worker
        self._start_speech_worker()
        self._start_listeners()
        self._speak(self.config.agent_names[0] if self.config.agent_names else None, "Nova online.")
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
            from nova import voices
            fallback = voices.get("piper:en_US-ryan-high")
            for agent in self.config.agent_names:
                key = self.config.voice_for(agent)
                entry = voices.get(key) or fallback
                if entry is fallback and key != fallback["key"]:
                    log(f"[{agent}] unknown voice '{key}', falling back to {fallback['key']}", "warn")
                self.tts_engines[agent] = TTSEngine(entry)
                log(f"[{agent}] voice: {entry['key']}", "info")

            if with_stt:
                from nova.voice.stt import STTEngine
                from nova.voice.audio import AudioCapture
                from nova.streaming import StreamingTranscriber
                self.stt = STTEngine(
                    model_size=self.config.get("voice.stt_model", "large-v3-turbo"),
                    device=self.config.get("voice.stt_device", "cpu"),
                    compute_type=self.config.get("voice.stt_compute_type", "int8"),
                    cpu_threads=int(self.config.get("voice.stt_cpu_threads", 0)),
                )
                self.audio = AudioCapture()
                self.streamer = StreamingTranscriber(
                    self.stt,
                    chunk_s=float(self.config.get("voice.stream_chunk_s", 18)),
                    min_commit_s=float(self.config.get("voice.stream_min_commit_s", 2.5)),
                    min_silence_s=float(self.config.get("voice.stream_min_silence_s", 0.45)),
                    silence_thresh=float(self.config.get("voice.stream_silence_thresh", 0.012)),
                )
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
            # Debounce: ignore accidental double-fires (COSMIC key-repeat, etc.).
            now = time.monotonic()
            if now - self._last_toggle < self._debounce_s:
                return
            self._last_toggle = now

            if self._recording_agent:
                self._stop_and_process()   # stops against the ORIGINAL agent
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

        self._flush_speech()  # barge-in: drop queued/playing speech before we listen
        if not self.audio:
            from nova.voice.audio import AudioCapture
            self.audio = AudioCapture()

        if self.audio.start():
            self.streamer.reset()
            self._recording_agent = agent
            self._rec_started = time.monotonic()
            self._rec_active.set()
            self._poll_thread = threading.Thread(target=self._stream_poll_loop, daemon=True)
            self._poll_thread.start()
            play_sound(_SOUND_START)
            log(f"Listening for {agent}... (press again to send)", "ok")
            notify("Nova", f"Listening → {agent}")

    def _stream_poll_loop(self):
        """Transcribe completed chunks while recording, so stop is near-instant."""
        while self._rec_active.is_set():
            time.sleep(1.5)
            if not self._rec_active.is_set():
                break
            # Safety cap: end a runaway/very long take (still sends full text).
            if time.monotonic() - self._rec_started > self._max_record_s:
                log(f"Reached {self._max_record_s:.0f}s cap — auto-sending", "warn")
                self._toggle("__stop__")
                break
            buf = self.audio.get_buffer_copy() if self.audio else None
            with self._stt_lock:
                if not self._rec_active.is_set():
                    break
                try:
                    self.streamer.poll(buf)
                except Exception as e:
                    log(f"stream poll error: {e}", "warn")

    def _stop_and_process(self):
        agent = self._recording_agent
        self._recording_agent = None
        self._rec_active.clear()
        play_sound(_SOUND_STOP)
        final_audio = self.audio.stop() if self.audio else None
        threading.Thread(target=self._process, args=(agent, final_audio), daemon=True).start()

    def _process(self, agent, final_audio):
        # Let the streaming poll thread finish its current chunk first.
        if self._poll_thread:
            self._poll_thread.join(timeout=30)
        try:
            buf = final_audio if final_audio is not None else np.array([], dtype=np.float32)
            start = time.time()
            with self._stt_lock:
                text = self.streamer.finish(buf)
            if not text or not text.strip():
                log("No speech detected", "warn")
                self._speak(agent, "I didn't catch that.")
                return
            log(f"[{agent}] heard ({time.time()-start:.1f}s, {len(buf)/16000:.0f}s audio): {text}", "ok")

            if not self.relay or not self.relay.connected:
                self._speak(agent, "The relay isn't connected. Run nova login.")
                return

            bot = self.config.agent(agent)["bot"]
            timeout = float(self.config.agent(agent).get("reply_timeout_s", 180))
            log(f"[{agent}] asking...", "info")
            notify("Nova", f"{agent} is thinking…")

            reply = self.relay.ask(bot, text, timeout=timeout)
            if reply and reply.strip():
                log(f"[{agent}] reply: {reply[:200]}", "ok")
                self._speak(agent, reply)
            else:
                log(f"[{agent}] empty reply", "warn")
                self._speak(agent, "No answer came back.")
        except TimeoutError:
            log(f"[{agent}] timed out", "err")
            self._speak(agent, f"{agent} took too long to answer.")
        except Exception as e:
            log(f"[{agent}] error: {e}", "err")
            self._speak(agent, "Something went wrong reaching the agent.")

    # ------------------------------------------------------------------ speech (anti-echo)
    def _start_speech_worker(self):
        self._speech_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self._speech_thread.start()

    def _speech_worker(self):
        """Play queued replies one at a time, never while the mic is recording."""
        while self._running or not self._speech_q.empty():
            try:
                agent, text = self._speech_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                epoch = self._speech_epoch
                # Hold until the mic is idle; abandon if a barge-in flush occurs.
                while self._rec_active.is_set() and self._running and epoch == self._speech_epoch:
                    time.sleep(0.1)
                tts = self.tts_engines.get(agent)
                if tts and self._running and epoch == self._speech_epoch:
                    tts.speak(text, blocking=True)
            except Exception as e:
                log(f"speech error ({agent}): {e}", "warn")
            finally:
                self._speech_q.task_done()

    def _speak(self, agent, text):
        if text and text.strip():
            self._speech_q.put((agent, text.strip()))

    def _flush_speech(self):
        """Drop queued speech and stop any current playback (for barge-in)."""
        self._speech_epoch += 1   # invalidate any speech the worker is holding
        try:
            while True:
                self._speech_q.get_nowait()
                self._speech_q.task_done()
        except queue.Empty:
            pass
        for tts in self.tts_engines.values():
            tts.stop()

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
            self._speak(agent, reply)
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
        self._rec_active.clear()
        self._running = False
        for tts in self.tts_engines.values():
            tts.stop()
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


def _voice_picker(config, agent=None):
    """Interactive TTS voice browser/selector — `nova tts-model [agent]`."""
    import subprocess as sp
    from nova import voices
    from nova.voice.synth import synth_to_wav
    from nova.config import selection_file

    if agent and agent not in config.agent_names:
        print(f"Unknown agent '{agent}'. Configured agents: {', '.join(config.agent_names)}")
        return

    PHRASE = ("Pixel Bot online. All systems nominal. I'm detecting multiple "
              "lifeforms in the region. How can I help you today?")
    preview_dir = os.path.expanduser("~/.nova/voice_previews")
    os.makedirs(preview_dir, exist_ok=True)
    items = voices.VOICES
    current = [config.voice_for(agent) if agent else None]

    def show():
        cat = None
        for i, v in enumerate(items):
            if v["cat"] != cat:
                cat = v["cat"]
                print(f"\n{C.CYAN}== {cat} =={C.RESET}")
            mark = f"{C.GREEN} ●{C.RESET}" if v["key"] == current[0] else "  "
            print(f"{i:3}{mark} {C.BOLD}{v['key']:34}{C.RESET} {C.GRAY}{v.get('desc','')}{C.RESET}")
        print(f"\n{C.GRAY}[number]=play   u <n>=use it   c=current   l=list   q=quit{C.RESET}")

    def preview_path(v):
        return os.path.join(preview_dir, v["key"].replace(":", "_").replace("/", "_") + ".wav")

    def play(v):
        path = preview_path(v)
        if not os.path.exists(path):
            print(f"  {C.GRAY}synthesizing {v['key']}...{C.RESET}", flush=True)
            try:
                synth_to_wav(v, PHRASE, path)
            except Exception as e:
                print(f"  {C.RED}synth failed: {e}{C.RESET}")
                return
        print(f"  {C.GREEN}▶ playing:{C.RESET} {v['key']}  {C.GRAY}({v.get('desc','')}){C.RESET}")
        try:
            sp.run(["aplay", "-q", path])
        except KeyboardInterrupt:
            print("  (skipped)")

    target = f" for {C.BOLD}{agent}{C.RESET}" if agent else " (browse-only — pass an agent to select, e.g. `nova tts-model pixelbot`)"
    print(f"{C.BOLD}Nova voice picker{C.RESET}{target} — {len(items)} voices.")
    if agent:
        print(f"Current: {C.GREEN}{current[0]}{C.RESET}")
    show()
    while True:
        try:
            raw = input(f"\n{C.GREEN}voice>{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if raw in ("q", "quit", "exit"):
            break
        if raw in ("l", "list"):
            show()
        elif raw in ("c", "current"):
            print(f"  current: {current[0] or '(no agent selected — pass one on the command line)'}")
        elif raw.split()[0] in ("u", "use"):
            if not agent:
                print(f"  {C.RED}no agent selected — run `nova tts-model <agent>` instead{C.RESET}")
                continue
            parts = raw.split()
            if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) < len(items):
                v = items[int(parts[1])]
                selection_file(agent).write_text(v["key"])
                current[0] = v["key"]
                print(f"  {C.GREEN}✓ {agent}'s voice set to {v['key']}{C.RESET}")
                r = input("  restart nova.service now to apply? [y/N] ").strip().lower()
                if r == "y":
                    sp.run(["systemctl", "--user", "restart", "nova.service"])
                    print("  restarted — it'll be live in ~20s.")
                else:
                    print("  will apply on next service restart.")
            else:
                print("  usage: u <number>")
        elif raw.isdigit() and int(raw) < len(items):
            play(items[int(raw)])
        else:
            print("  ? enter a number to play, 'u <n>' to select, or 'q'")
    print("done.")


def main():
    import argparse
    from nova.config import Config

    parser = argparse.ArgumentParser(description="Nova voice bridge to Hermes")
    parser.add_argument("--daemon", action="store_true",
                        help="Headless service mode (no terminal input loop)")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("login", help="One-time Telegram user login")
    sub.add_parser("setup", help="List bot chats to configure agents")
    tts_model = sub.add_parser("tts-model", help="Browse and pick a per-agent TTS voice")
    tts_model.add_argument("agent", nargs="?", default=None,
                           help="Agent to set the voice for (e.g. pixelbot, jailbreak). Omit to just browse.")
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
    if args.cmd == "tts-model":
        _voice_picker(config, agent=args.agent)
        return
    if args.cmd == "ask":
        bridge = VoiceBridge(config)
        bridge._connect_relay()
        if not bridge.relay:
            sys.exit(1)
        bridge._load_models(with_stt=False)  # text-only path needs just TTS
        bridge._running = True
        bridge._start_speech_worker()
        bridge._send_text(args.agent, " ".join(args.message))
        # wait for the reply to finish speaking
        tts = bridge.tts_engines.get(args.agent)
        for _ in range(1200):
            if bridge._speech_q.empty() and not (tts and tts.is_speaking()):
                break
            time.sleep(0.1)
        return

    # Headless when asked, or when there's no terminal (i.e. run as a service).
    headless = args.daemon or not sys.stdin.isatty()
    VoiceBridge(config).run(headless=headless)


if __name__ == "__main__":
    main()
