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
    ├── stt.py   # faster-whisper large-v3 (CUDA, CPU fallback)
    └── tts.py   # Piper (en_US-ryan-high)
nova            # launcher      nova-toggle   # socket poke for COSMIC keybinds
```

## Setup

```bash
cd ~/Desktop/Projects/Archived/Dictation

# 1. Environment (reuses system torch/faster-whisper via --system-site-packages)
uv venv --python 3.12 --system-site-packages .venv
uv pip install --python .venv/bin/python -r requirements.txt

# 2. Voice models  (Piper voice → ~/.nova/models/piper/, Whisper auto-downloads)
mkdir -p ~/.nova/models/piper
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high
curl -fsSL -o ~/.nova/models/piper/en_US-ryan-high.onnx      $BASE/en_US-ryan-high.onnx
curl -fsSL -o ~/.nova/models/piper/en_US-ryan-high.onnx.json $BASE/en_US-ryan-high.onnx.json

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
```

### COSMIC keybinds

Settings → Keyboard → Custom Shortcuts → Add:

| Shortcut | Command |
|----------|---------|
| F4 | `/home/wonka/Desktop/Projects/Archived/Dictation/nova-toggle pixelbot` |
| F8 | `/home/wonka/Desktop/Projects/Archived/Dictation/nova-toggle jailbreak` |

## Usage

```bash
./nova                          # run the bridge
# press F4, speak, press F4 → Pixel Bot answers by voice
# press F8, speak, press F8 → Jailbreak answers by voice

./nova ask pixelbot "what's on my calendar today"   # one-shot text → voice reply
```

In the terminal you can also type `pixelbot: <text>` or `/voice jailbreak`.

## Requirements & known constraints

- **GPU driver:** faster-whisper uses CUDA on the RTX 3090s. If `nvidia-smi` reports
  a *driver/library version mismatch*, CUDA is unavailable until a **reboot** and STT
  silently falls back to CPU (~1.5× real-time — correct but slow).
- **VRAM contention:** both 3090s serve the `llama-heretic-q8` model (layer-split).
  After a reboot, check `nvidia-smi` free VRAM — Whisper `large-v3` needs ~3 GB. If
  there isn't headroom, set `voice.stt_device: cpu` in `~/.nova/config.yaml` (or use a
  smaller model like `distil-large-v3`) so STT never competes with the heretic.
- **Audio:** capture uses `arecord` (ALSA/PipeWire); playback uses `aplay`. No PortAudio.
- **Telegram:** Nova logs in as your user account (a userbot). The session file
  `~/.nova/nova.session` is an auth credential — it is gitignored; never share it.
