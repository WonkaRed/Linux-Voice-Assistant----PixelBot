"""
Volume Control Tool - Audio control for intelligent path.

Provides volume control functionality when fast path misses the query.
"""
import logging
import subprocess
from typing import Dict, Any

from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class VolumeControlTool(BaseTool):
    """Control system volume via PulseAudio (pactl)."""

    def _get_name(self) -> str:
        return "control_volume"

    def _get_description(self) -> str:
        return """Control system audio volume (mute, unmute, set volume).
Use this when user asks to mute/unmute or adjust volume."""

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Volume action to perform",
                    "enum": ["mute", "unmute", "set", "get"]
                },
                "volume_percent": {
                    "type": "integer",
                    "description": "Volume level (0-100, only for 'set' action)"
                }
            },
            "required": ["action"]
        }

    def execute(self, **kwargs) -> str:
        """
        Execute volume control action.

        Args:
            action: Volume action (mute, unmute, set, get)
            volume_percent: Volume level for 'set' action

        Returns:
            str: Result message
        """
        try:
            action = kwargs.get("action")
            volume_percent = kwargs.get("volume_percent", 50)

            if action == "mute":
                return self._mute()
            elif action == "unmute":
                return self._unmute()
            elif action == "set":
                return self._set_volume(volume_percent)
            elif action == "get":
                return self._get_volume()
            else:
                return f"Unknown action: {action}"

        except Exception as e:
            logger.error(f"Volume control failed: {e}", exc_info=True)
            return f"Failed to control volume: {e}"

    def _mute(self) -> str:
        """Mute audio."""
        try:
            subprocess.run(
                ['pactl', 'set-sink-mute', '@DEFAULT_SINK@', '1'],
                check=True,
                capture_output=True
            )
            logger.info("Audio muted")
            return "Muted"
        except subprocess.CalledProcessError as e:
            return f"Failed to mute: {e}"

    def _unmute(self) -> str:
        """Unmute audio."""
        try:
            subprocess.run(
                ['pactl', 'set-sink-mute', '@DEFAULT_SINK@', '0'],
                check=True,
                capture_output=True
            )
            logger.info("Audio unmuted")
            return "Unmuted"
        except subprocess.CalledProcessError as e:
            return f"Failed to unmute: {e}"

    def _set_volume(self, percent: int) -> str:
        """Set volume to specific percentage."""
        try:
            # Clamp to 0-100
            percent = max(0, min(100, percent))

            subprocess.run(
                ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{percent}%'],
                check=True,
                capture_output=True
            )
            logger.info(f"Volume set to {percent}%")
            return f"Volume set to {percent} percent"
        except subprocess.CalledProcessError as e:
            return f"Failed to set volume: {e}"

    def _get_volume(self) -> str:
        """Get current volume level."""
        try:
            result = subprocess.run(
                ['pactl', 'get-sink-volume', '@DEFAULT_SINK@'],
                check=True,
                capture_output=True,
                text=True
            )

            # Parse output: "Volume: front-left: 65536 /  100% / 0.00 dB..."
            output = result.stdout
            if '/' in output:
                parts = output.split('/')
                for part in parts:
                    part = part.strip()
                    if '%' in part:
                        volume_str = part.replace('%', '').strip()
                        return f"Volume is at {volume_str} percent"

            return "Could not determine volume level"

        except subprocess.CalledProcessError as e:
            return f"Failed to get volume: {e}"
