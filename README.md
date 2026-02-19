# Nova Voice Assistant

GPU-accelerated push-to-talk voice bridge to Pixel Bot, with local desktop tools.

## Quick Start

```bash
./nova
```

Press F4 to toggle voice recording, speak your command, press F4 again.

## Features

| Feature | Description |
|---------|-------------|
| **Voice Control** | Push-to-talk via F4 hotkey (Wayland-compatible via socket) |
| **4 Local Tools** | System stats, clipboard, timer, notes |
| **Pixel Bot** | Claude Sonnet via SSH for everything else |
| **Piper TTS** | High-quality neural voice (en_US-ryan-high) |
| **CUDA STT** | GPU-accelerated faster-whisper large-v3 |

## Architecture

```
src/nova/
├── agent.py           # Hybrid agent: regex local routing + Pixel Bot bridge
├── llm.py             # Pixel Bot client (SSH + CLI)
├── runner.py          # Main runner with voice + terminal UI
├── config.py          # YAML config (~/.nova/config.yaml)
├── voice/
│   ├── stt.py         # Speech-to-text (faster-whisper, CUDA)
│   ├── tts.py         # Text-to-speech (Piper, ryan-high)
│   └── interface.py   # Voice orchestration
└── tools/
    ├── system_stats.py # CPU/GPU/RAM/disk/temp
    ├── clipboard.py    # Read/write clipboard
    ├── timer.py        # Named timers + notifications
    └── notes.py        # Quick notes (~/.nova/notes/)
```

## Requirements

- **GPU**: NVIDIA with CUDA support (RTX 3090 24GB)
- **OS**: Linux (Pop!_OS 24.04 with COSMIC/Wayland)
- **SSH**: Access to pixel-labs-server (10.0.0.75) with ControlMaster

## Installation

```bash
cd ~/Desktop/Projects/Dictation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./nova
```

## Pixel Bot SSH Setup

Nova connects to Pixel Bot via SSH. Configure `~/.ssh/config`:

```
Host pixel-labs-server
    HostName 10.0.0.75
    User wonka
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 600
```

Test connectivity: `ssh pixel-labs-server 'echo pong'`

## Single-Shot Query

```bash
./nova --query "what's my GPU temp"
# or
./nova -q "set a timer for 5 minutes"
```

## Wayland Support

Nova uses a Unix socket for F4 hotkey support on Wayland:

```bash
# Configure COSMIC shortcut:
# Settings > Keyboard > Custom Shortcuts > Add
# Command: /home/wonka/Desktop/Projects/Dictation/nova-toggle
# Shortcut: F4
```

## Files

- `nova` — Main launcher script
- `nova-toggle` — Socket toggle for Wayland hotkey
- `src/nova/` — Core Python modules
- `models/piper/` — TTS voice model (ryan-high)
- `.env` — API keys (not committed)
