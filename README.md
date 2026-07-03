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
├── main.py      # orchestrator: hotkeys → STT → relay → TTS, + login/setup/ask
├── config.py    # ~/.nova/config.yaml loader; Telegram creds from env
├── relay.py     # Telethon user-client: send to a bot, read the reply
├── hotkey.py    # Unix-socket toggle (Wayland) + evdev fallback
└── voice/
    ├── audio.py # microphone capture via arecord/parec/ffmpeg (no PortAudio)
    ├── stt.py   # faster-whisper large-v3-turbo on CPU (int8, all cores)
    └── tts.py   # Piper (en_US-ryan-high)
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
# Kokoro (40+ voices) for `nova tts-model`
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
./nova tts-model                                     # browse 40+ voices, preview, pick one
./nova                                               # foreground/interactive (stop the service first)
```

**Voices:** `nova tts-model` is an interactive picker — type a number to hear a
voice, `u <n>` to make it the active one (Kokoro + Piper voices, plus robot/
character styles like GLaDOS-ish, HAL, Dalek, PDA). It restarts the service to
apply.

Interactively you can also type `pixelbot: <text>` or `/voice jailbreak`.

## Requirements & known constraints

- **STT/TTS run on CPU by default** (turbo int8, all cores; ~1.1 GB RAM, zero VRAM)
  so voice never competes with the dual-3090 heretic model. The service is niced low
  and yields CPU to everything else.
- **Want near-instant STT on GPU?** Set `voice.stt_device: cuda` +
  `voice.stt_compute_type: float16` in `~/.nova/config.yaml`. Only do this if
  `nvidia-smi` shows ≳3 GB free VRAM — otherwise it fights the heretic. (Requires a
  working driver; a *driver/library version mismatch* means CUDA is down until reboot.)
- **Audio:** capture via `arecord` (ALSA/PipeWire), playback via `aplay`. No PortAudio.
- **Telegram:** logs in as your user account. `~/.nova/nova.session` is an auth
  credential — gitignored; never share it.
- **Audio:** capture uses `arecord` (ALSA/PipeWire); playback uses `aplay`. No PortAudio.
- **Telegram:** Nova logs in as your user account (a userbot). The session file
  `~/.nova/nova.session` is an auth credential — it is gitignored; never share it.
