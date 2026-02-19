"""
Nova Server Configuration.
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 9600,
        "auth_token": "",
    },
    "pixelbot": {
        "agent_name": "main",
        "session_id": "nova-desktop",
        "timeout": 15,
        "max_retries": 1,
        "retry_delay": 2.0,
    },
    "soul": {
        "directory": "soul",
    },
}


class ServerConfig:
    """Server configuration manager."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path(__file__).parent.parent / "config.yaml"
        self._config: Dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load config from YAML, merge with defaults."""
        self._config = self._deep_copy(DEFAULT_CONFIG)

        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    user_config = yaml.safe_load(f) or {}
                self._config = self._deep_merge(self._config, user_config)
                logger.info(f"Loaded config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config: {e}. Using defaults.")
        else:
            logger.warning(f"Config not found at {self.config_path}, using defaults")

    def _deep_copy(self, d: Dict) -> Dict:
        """Deep copy a dict."""
        result = {}
        for k, v in d.items():
            result[k] = self._deep_copy(v) if isinstance(v, dict) else v
        return result

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge override into base."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Get value by dot-notation key."""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def host(self) -> str:
        return self.get("server.host", "0.0.0.0")

    @property
    def port(self) -> int:
        return self.get("server.port", 9600)

    @property
    def auth_token(self) -> str:
        return self.get("server.auth_token", "")

    @property
    def pixelbot(self) -> Dict[str, Any]:
        return self._config.get("pixelbot", {})

    @property
    def soul_dir(self) -> Path:
        rel = self.get("soul.directory", "soul")
        return self.config_path.parent / rel
