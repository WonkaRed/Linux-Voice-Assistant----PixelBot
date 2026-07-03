"""
Configuration loader for the Nova voice bridge.

Non-secret settings live in ~/.nova/config.yaml (agents, models, timeouts,
keybinds). Telegram *user* API credentials (api_id / api_hash) are secrets and
are read from the environment — sourced by the launcher from
~/.claude/secrets/clients/pixel-labs/telegram-user.env — never from this repo.
"""
import copy
import os
from pathlib import Path
from typing import Any, Optional

import yaml

CONFIG_DIR = Path(os.environ.get("NOVA_HOME", str(Path.home() / ".nova")))
CONFIG_PATH = CONFIG_DIR / "config.yaml"
# The `nova tts-model` picker writes the chosen voice key here (kept separate so
# selecting a voice never rewrites/strips the user's commented config.yaml).
SELECTION_FILE = CONFIG_DIR / "voice.selection"

# Sensible defaults. Everything here can be overridden by ~/.nova/config.yaml.
DEFAULTS: dict = {
    "telegram": {
        # api_id / api_hash come from the environment (see module docstring).
        # session is the Telethon user-session file (login persisted here).
        "session": str(CONFIG_DIR / "nova.session"),
        # Optional: pin the user id we log in as, for a sanity check on startup.
        "user_id": None,
    },
    "agents": {
        "pixelbot": {
            # Telegram target for the Pixel Bot gateway. May be an @username,
            # a numeric chat/user id, or a "t.me/..." link. Resolved once and
            # cached in the Telethon session.
            "bot": "@PixelBot",
            "reply_timeout_s": 180,  # cloud agent + tools can be slow
        },
        "jailbreak": {
            "bot": "@JailbreakBot",
            "reply_timeout_s": 150,  # local heretic on the RTX 3090
        },
    },
    "voice": {
        # Active TTS voice — a key from nova.voices (set via `nova tts-model`).
        "selection": "piper:en_US-ryan-high",
        # turbo on CPU ≈ large-v3 accuracy at ~0.6× real-time, zero VRAM use —
        # so STT never competes with the GPU model inference.
        "stt_model": "large-v3-turbo",
        "stt_device": "cpu",                  # cpu keeps us submissive to the GPUs
        "stt_compute_type": "int8",           # int8 for cpu; float16 for cuda
        "stt_cpu_threads": 0,                 # 0 = use all cores
        "tts_voice": str(CONFIG_DIR / "models" / "piper" / "en_US-ryan-high.onnx"),
        "tts_effect": None,                   # optional ffmpeg filter chain (robotic voice)
        # Streaming STT: commit finished speech at pauses while you talk, so the
        # post-stop wait is tiny. Tune silence_thresh up if a noisy mic never
        # "pauses"; down if it splits too eagerly.
        "stream_chunk_s": 9,                 # force a cut after this much unbroken speech
        "stream_min_commit_s": 2.0,           # don't commit fragments shorter than this
        "stream_min_silence_s": 0.3,         # a pause this long is a commit boundary
        "stream_silence_thresh": 0.02,       # RMS (on [-1,1]) below this counts as silence
        "max_record_s": 720,                  # 12 min safety cap (still sends the full transcript)
    },
    # How the relay decides the bot has finished answering: after the first
    # reply arrives, keep collecting until this many seconds pass with no new
    # message or edit (covers Hermes streaming its answer as edits).
    "relay": {
        "settle_s": 2.5,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into a copy of base."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Dot-path accessor over merged defaults + ~/.nova/config.yaml."""

    def __init__(self, data: dict):
        self._data = data

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        path = Path(path) if path else CONFIG_PATH
        user_data: dict = {}
        if path.exists():
            loaded = yaml.safe_load(path.read_text()) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"{path} must be a YAML mapping, got {type(loaded).__name__}")
            user_data = loaded
        merged = _deep_merge(DEFAULTS, user_data)
        # The picker's selection file wins over config.yaml for the voice.
        if SELECTION_FILE.exists():
            sel = SELECTION_FILE.read_text().strip()
            if sel:
                merged.setdefault("voice", {})["selection"] = sel
        return cls(merged)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def agent(self, name: str) -> dict:
        """Return the config block for an agent, or raise if unknown."""
        agents = self._data.get("agents", {})
        if name not in agents:
            known = ", ".join(agents) or "(none)"
            raise KeyError(f"Unknown agent '{name}'. Configured agents: {known}")
        return agents[name]

    @property
    def agent_names(self) -> list:
        return list(self._data.get("agents", {}).keys())

    def expanduser(self, dotted: str, default: Any = None) -> Optional[str]:
        """Get a path setting with ~ expanded."""
        value = self.get(dotted, default)
        return os.path.expanduser(value) if value else value


def telegram_credentials() -> tuple:
    """
    Read Telegram *user* API credentials from the environment.

    Returns (api_id: int, api_hash: str). Raises RuntimeError with guidance if
    they are missing so the failure is actionable rather than cryptic.
    """
    api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise RuntimeError(
            "Missing TELEGRAM_API_ID / TELEGRAM_API_HASH.\n"
            "Get them from https://my.telegram.org (API development tools), then put:\n"
            "  TELEGRAM_API_ID=...\n  TELEGRAM_API_HASH=...\n"
            "in ~/.claude/secrets/clients/pixel-labs/telegram-user.env\n"
            "(the `nova` launcher sources that file automatically)."
        )
    try:
        return int(api_id), api_hash
    except ValueError:
        raise RuntimeError(f"TELEGRAM_API_ID must be an integer, got '{api_id}'.")
