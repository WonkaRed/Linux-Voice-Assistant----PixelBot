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
| Pixel Bot (F4) | **No Man's Sky exosuit AI** — the genuine xVASynth voice model | `real:nms_suit` |
| Jailbreak (F8) | **HAL 9000** — genuine RVC v2 model trained on Douglas Rain's film dialogue | `real:hal9000` |

These are real trained models, not effects on a generic voice — pulled from
their original sources (see the commit history for exactly where). A third
real model, GLaDOS (Forward Tacotron+HiFiGAN, the actual Portal checkpoint),
is also in the catalog as `real:glados` if you want to switch either agent to it.

`nova tts-model <agent>` also has 70 other voices to browse: natural Kokoro/Piper
voices plus ffmpeg-effect robot styles (JARVIS-ish, EDI-ish, Cortana-ish,
Terminator-ish, etc. — approximations, not trained models).

Each real-model engine (`~/.nova/glados/`, `~/.nova/xvasynth/`, `~/.nova/rvc/`) is
self-contained with its own venv. HAL 9000 (RVC) runs behind a persistent
background server (`~/.nova/rvc/rvc_server.py`, auto-started on first use,
listens on `/tmp/nova-rvc.sock`) so replies come back in a few seconds instead
of reloading its ~350 MB of weights on every line.

## Requirements & known constraints

- **Nova never touches the GPU — by hard requirement, not just default.** STT
  (turbo int8, all cores, ~1.1 GB RAM) and every TTS engine (Kokoro, Piper,
  GLaDOS, xVASynth, RVC) run CPU-only. The RVC and xVASynth/GLaDOS venvs use
  CPU-only torch builds specifically so this holds even if a config value were
  changed by mistake — the GPUs are reserved entirely for model inference
  (the dual-3090 heretic). Do not set `voice.stt_device: cuda` or point any
  voice engine at `cuda`/`gpu`.
- **Audio:** capture via `arecord` (ALSA/PipeWire), playback via `aplay`. No PortAudio.
- **Telegram:** logs in as your user account (a userbot). `~/.nova/nova.session` is
  an auth credential — gitignored; never share it.
