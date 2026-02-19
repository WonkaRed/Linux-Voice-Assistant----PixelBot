"""
Nova Configuration System - Centralized settings management.

Features:
- YAML-based configuration
- Defaults with user overrides
- Config stored in ~/.nova/config.yaml
- Environment variable support
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# Configuration directory
CONFIG_DIR = Path.home() / ".nova"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
HISTORY_DIR = CONFIG_DIR / "history"
NOTES_DIR = CONFIG_DIR / "notes"

# Default configuration
DEFAULT_CONFIG = {
    # Pixel Bot settings
    "pixelbot": {
        "ssh_host": "pixel-labs-server",  # SSH config alias
        "agent_name": "main",
        "session_id": "nova-desktop",
        "timeout": 15,
        "max_retries": 1,
        "retry_delay": 2.0,
    },

    # Voice settings
    "voice": {
        "stt_model": "large-v3",  # tiny.en, base.en, small.en, medium.en, large-v3
        "stt_device": "cuda",
        "stt_compute_type": "float16",
        "tts_voice": None,  # None = use default Piper voice
        "sample_rate": 16000,
    },

    # Weather defaults
    "weather": {
        "default_location": "30180",  # Villa Rica, GA
        "default_city": "Villa Rica, GA",
    },

    # Server monitor
    "servers": {
        "default": {
            "host": "10.0.0.75",
            "user": "wonka",
            "name": "Local Server",
        },
        # Additional servers can be added here
    },

    # History/persistence
    "history": {
        "save_conversations": True,
        "max_saved_sessions": 50,
        "auto_save": True,
    },

    # UI settings
    "ui": {
        "notifications": True,
        "hotkey": "f4",
        "auto_load_agent": True,
    },

    # Nova Server connection (node mode)
    "server": {
        "url": "ws://10.0.0.75:9600",
        "auth_token": "",
        "reconnect_max_delay": 30,
    },

    # VRAM management
    "vram": {
        "unload_threshold_gb": 4.0,
        "reload_threshold_gb": 8.0,
        "poll_interval_s": 1.0,
        "hysteresis_s": 10.0,
        "monitored_processes": ["comfyui", "python", "blender", "resolve"],
    },
}


class Config:
    """Configuration manager for Nova."""

    _instance: Optional['Config'] = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize configuration (only once)."""
        if self._initialized:
            return

        self._initialized = True
        self._ensure_directories()
        self._load_config()

    def _ensure_directories(self):
        """Create necessary directories."""
        for directory in [CONFIG_DIR, HISTORY_DIR, NOTES_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_config(self):
        """Load configuration from file, merging with defaults."""
        self._config = DEFAULT_CONFIG.copy()

        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    user_config = yaml.safe_load(f) or {}

                # Deep merge user config into defaults
                self._config = self._deep_merge(self._config, user_config)
                logger.info(f"Loaded config from {CONFIG_FILE}")

            except Exception as e:
                logger.warning(f"Failed to load config: {e}. Using defaults.")
        else:
            # Create default config file
            self.save()
            logger.info(f"Created default config at {CONFIG_FILE}")

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def save(self):
        """Save current configuration to file."""
        try:
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Saved config to {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Config key (e.g., "llm.model", "voice.stt_model")
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any, save: bool = True):
        """
        Set a configuration value using dot notation.

        Args:
            key: Config key (e.g., "llm.model")
            value: Value to set
            save: Whether to save to file immediately
        """
        keys = key.split('.')
        target = self._config

        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]

        target[keys[-1]] = value

        if save:
            self.save()

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get an entire configuration section."""
        return self._config.get(section, {}).copy()

    @property
    def pixelbot(self) -> Dict[str, Any]:
        """Get Pixel Bot configuration."""
        return self.get_section("pixelbot")

    @property
    def voice(self) -> Dict[str, Any]:
        """Get voice configuration."""
        return self.get_section("voice")

    @property
    def weather(self) -> Dict[str, Any]:
        """Get weather configuration."""
        return self.get_section("weather")

    @property
    def servers(self) -> Dict[str, Any]:
        """Get servers configuration."""
        return self.get_section("servers")

    @property
    def history(self) -> Dict[str, Any]:
        """Get history configuration."""
        return self.get_section("history")

    @property
    def ui(self) -> Dict[str, Any]:
        """Get UI configuration."""
        return self.get_section("ui")

    def __repr__(self) -> str:
        return f"Config({CONFIG_FILE})"


# Global config instance
def get_config() -> Config:
    """Get the global configuration instance."""
    return Config()


# Convenience functions
def get(key: str, default: Any = None) -> Any:
    """Get a config value."""
    return get_config().get(key, default)


def set_config(key: str, value: Any, save: bool = True):
    """Set a config value."""
    get_config().set(key, value, save)
