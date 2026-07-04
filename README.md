# Nova — voice bridge to the Hermes agents

Push a key, talk, hear the answer. Nova is a **thin voice relay**: it transcribes
your speech locally, hands the text to one of your Hermes agents on `10.0.0.75`,
and speaks the reply back. All the agent work — memory, tools, personality —
happens in Hermes. This machine only does speech in / speech out.

```
        F4                                   F8
   ┌──────────┐                        ┌──────────┐
   │ Pixel Bot│                        │ Jailbreak│
   └────┬─────┘                        └────┬─────┘
        │  Telegram (as you)                │
        ▼                                   ▼
  press F4/F8 → arecord → Whisper STT → send to the agent's Telegram bot
  → Hermes gateway handles it in the canonical Telegram session (zero race)
  → bot replies in Telegram → Nova reads the reply → Piper TTS speaks it here
```

Because the message reaches the bot as a normal Telegram DM from you, the running
Hermes **gateway** is the single owner of that chat's session — so your voice turn
lands in the *real* Telegram thread (shared memory, full context) with no risk of
racing a second agent runner. The reply is spoken here and also visible in Telegram.

## Agents

| Key | Agent      | Hermes profile (on 10.0.0.75) | Inference |
|-----|------------|-------------------------------|-----------|
| F4  | Pixel Bot  | `default`                     | cloud (DeepSeek) |
| F8  | Jailbreak  | `jailbreak`                   | local `qwen3.6-heretic-q8` (served from this desktop's `:8078`) |

## Layout

```
src/nova/
├── main.py       # orchestrator: hotkeys → STT → relay → per-agent TTS, + login/setup/ask/tts-model
├── config.py     # ~/.nova/config.yaml loader; per-agent voice selection; Telegram creds from env
├── relay.py      # Telethon user-client: send to a bot, read the reply
├── hotkey.py     # Unix-socket toggle (Wayland) + evdev fallback
├── voices.py     # voice catalog: Kokoro/Piper voices + real character models + robot effect styles
└── voice/
    ├── audio.py  # microphone capture via arecord/parec/ffmpeg (no PortAudio)
    ├── stt.py    # faster-whisper large-v3-turbo on CPU (int8, all cores)
    ├── synth.py  # dispatches synthesis by engine: kokoro/piper/glados/xvasynth/rvc
    └── tts.py    # playback (interruptible) over synth.py
nova            # launcher      nova-toggle   # socket poke for COSMIC keybinds
nova.service    # systemd --user unit (autostart, self-restart, reboot-proof)
```

## Runs as a service

Nova runs as a `systemd --user` service — starts on login, restarts itself on
failure, survives reboots, and is niced/CPU-weighted low so it always yields to
the model inference. STT + TTS run on **CPU** (turbo ≈ large-v3 accuracy at
~0.6× real-time, ~1.1 GB RAM, **zero VRAM**), so voice never competes with the
dual-3090 heretic model.

```bash
./setup-autostart.sh                        # install + enable + start
systemctl --user status nova.service        # check
journalctl --user -u nova.service -f        # logs
```

## Setup

```bash
cd ~/Desktop/Projects/Archived/Dictation

# 1. Environment (reuses system torch/faster-whisper via --system-site-packages)
uv venv --python 3.12 --system-site-packages .venv
uv pip install --python .venv/bin/python -r requirements.txt

# 2. Voice models  (Whisper auto-downloads; Piper + Kokoro for TTS)
mkdir -p ~/.nova/models/piper ~/.nova/models/kokoro
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high
curl -fsSL -o ~/.nova/models/piper/en_US-ryan-high.onnx      $BASE/en_US-ryan-high.onnx
curl -fsSL -o ~/.nova/models/piper/en_US-ryan-high.onnx.json $BASE/en_US-ryan-high.onnx.json
# Kokoro (multi-voice) for `nova tts-model`
KO=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
curl -fsSL -o ~/.nova/models/kokoro/kokoro-v1.0.onnx $KO/kokoro-v1.0.onnx
curl -fsSL -o ~/.nova/models/kokoro/voices-v1.0.bin  $KO/voices-v1.0.bin

# 3. Config
cp config.example.yaml ~/.nova/config.yaml   # then edit the bot @usernames if needed

# 4. Telegram user credentials (SECRET — not in this repo)
#    Get api_id / api_hash from https://my.telegram.org → API development tools:
cat > ~/.claude/secrets/clients/pixel-labs/telegram-user.env <<'EOF'
TELEGRAM_API_ID=1234567
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
EOF

# 5. One-time Telegram login (phone number → code → 2FA if set)
./nova login

# 6. Confirm the bot chat targets, then set them in ~/.nova/config.yaml
./nova setup     # lists your bot chats with @username and id

# 7. Install as a service (autostart, self-restart, reboot-proof)
./setup-autostart.sh
```

(The Whisper `large-v3-turbo` model auto-downloads on first run — no manual step.)

### COSMIC keybinds

Settings → Keyboard → Custom Shortcuts → Add:

| Shortcut | Command |
|----------|---------|
| F4 | `/home/wonka/Desktop/Projects/Archived/Dictation/nova-toggle pixelbot` |
| F8 | `/home/wonka/Desktop/Projects/Archived/Dictation/nova-toggle jailbreak` |

## Usage

Once installed as a service it's always running — just press the keys:

- **F4** → speak → F4 → Pixel Bot answers by voice
- **F8** → speak → F8 → Jailbreak answers by voice

Talk as long as you like — up to a 12-minute safety cap (and even hitting the cap
sends your **full** transcript). Long takes are transcribed in the background
*while* you speak, so stopping returns the whole thing almost immediately. An
ascending chime means "listening", a descending one means "captured/sending".
The agent's spoken reply never plays while the mic is live, so it can't echo back
into your next message.

```bash
./nova ask pixelbot "what's on my calendar today"   # one-shot text → voice reply
./nova tts-model pixelbot                            # browse voices, pick pixelbot's
./nova tts-model jailbreak                           # ...or jailbreak's
./nova tts-model                                     # browse-only, no agent argument to set
./nova                                               # foreground/interactive (stop the service first)
```

Interactively you can also type `pixelbot: <text>` or `/voice jailbreak`.

## Voices

Each agent has its **own** voice, set in `agents.<name>.voice` (or via
`nova tts-model <agent>` → `u <n>`, which writes `~/.nova/voice.selection.<agent>`
and overrides config.yaml). Defaults:

| Agent | Voice | Engine |
|-------|-------|--------|
| Pixel Bot (F4) | **Subnautica Cyclops AI** — genuine RVC v2 model (500 epochs) | `real:cyclops` |
| Jailbreak (F8) | **HAL 9000** — genuine RVC v2 model trained on Douglas Rain's film dialogue | `real:hal9000` |

These are real trained models, not effects on a generic voice — pulled from
their original sources (see git history for exactly where; the catalog was
trimmed 2026-07-03 down to just what's used — a 70-voice version with
Kokoro/Piper naturals and ffmpeg-effect robot approximations existed earlier
if any of that is wanted back). A third real model, GLaDOS (Forward
Tacotron+HiFiGAN, the actual Portal checkpoint), is also in the catalog as
`real:glados` if you want to switch either agent to it.

**Server-side prerequisite:** both Hermes profiles (`default` and `jailbreak`
on 10.0.0.75) must have the `tts` toolset disabled
(`disabled_toolsets: [tts]` in `~/.hermes/config.yaml` and
`~/.hermes/profiles/jailbreak/config.yaml`, gateway restarted after). Without
this, the agent can decide mid-turn to call its own `text_to_speech` tool and
send Edge-TTS audio as a Telegram voice message instead of (or alongside) the
text Nova expects — bypassing the local character voice entirely. Verify with
`hermes tools list | grep tts` on the server (should show `✗ disabled`).

`nova tts-model <agent>` also has one fallback voice to browse:
`piper:en_US-ryan-high`, a plain natural male voice used automatically if a
configured real-model voice ever fails to load.

Each real-model engine (`~/.nova/glados/`, `~/.nova/rvc/`) is self-contained
with its own venv, rebuilt with CPU-only torch so the GPU is never touched.
HAL 9000 and Cyclops (both RVC) run behind a persistent background server
(`~/.nova/rvc/rvc_server.py`, auto-started on first use,
listens on `/tmp/nova-rvc.sock`) so replies come back in a few seconds instead
of reloading its ~350 MB of weights on every line.

## GPU-aware STT (opportunistic, safety-first)

STT (Whisper) can move itself onto a GPU when there's real, comfortable free
VRAM, and back to CPU the instant that margin gets tight — without ever
contending with ComfyUI, the heretic model, or anything else running on the
GPUs. On by default (`voice.gpu_dynamic.enabled: true`); everything else runs
CPU-only always (TTS — Kokoro, Piper, GLaDOS, RVC — never touches the GPU;
the RVC and GLaDOS venvs use CPU-only torch builds so this holds even if a
config value were changed by mistake).

How it decides:
- Needs **≥6144 MB free** (`load_threshold_mb`) before moving onto a GPU —
  real headroom beyond the model's own ~2.7-3.6 GB footprint, not just
  "technically fits." Picks whichever GPU has the most free room.
- Evicts back to CPU the moment free VRAM drops **below 3072 MB**
  (`unload_threshold_mb`) — deliberately a lower number than the load
  threshold, so a single reading near the boundary can't cause a flap.
- Checks **every ~12s** while resident on a GPU (fast reaction if something
  else needs the room) but only **every ~5 min** while on CPU
  (`cooldown_poll_s`) — no reason to hammer a GPU that's been maxed out for a
  while. Uses `pynvml` (a direct driver call, not `nvidia-smi` subprocesses),
  so even the fast cadence is cheap.
- Never interrupts an in-progress transcription — a switch either happens
  instantly (idle) or waits out the current chunk (bounded to a few seconds),
  using the same lock the streaming transcriber already holds.
- Logs every switch (`journalctl --user -u nova.service | grep -i gpu`) and
  sends a desktop notification.

Override any of the above in `~/.nova/config.yaml` under `voice.gpu_dynamic`
(`enabled`, `load_threshold_mb`, `unload_threshold_mb`, `active_poll_s`,
`cooldown_poll_s`, `compute_type`). Set `enabled: false` to pin STT to CPU
permanently.

## Requirements & known constraints

- **Audio:** capture via `arecord` (ALSA/PipeWire), playback via `aplay`. No PortAudio.
- **Telegram:** logs in as your user account (a userbot). `~/.nova/nova.session` is
  an auth credential — gitignored; never share it.
