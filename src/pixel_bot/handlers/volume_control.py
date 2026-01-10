"""
Volume Control Handler

Handles volume-related commands using PulseAudio (pactl).

Commands:
- set volume to X%
- increase/decrease volume [by X]
- mute/unmute
"""
import logging
import re
import subprocess
from typing import Optional, Tuple

from .base import BaseHandler

logger = logging.getLogger(__name__)


class VolumeControlHandler(BaseHandler):
    """Handles volume control via PulseAudio."""

    def handle(self, query: str, speak_response: bool = True) -> str:
        """
        Handle volume control query.

        Args:
            query: User query (e.g., "set volume to 50%")
            speak_response: Whether to speak response

        Returns:
            str: Response text
        """
        try:
            query_lower = query.lower()

            # Detect action type
            if re.search(r'\b(mute|silence)\b', query_lower) and not re.search(r'\bunmute\b', query_lower):
                response = self._mute()
            elif re.search(r'\bunmute\b', query_lower):
                response = self._unmute()
            elif re.search(r'\bincrease|raise|turn\s+up|louder\b', query_lower):
                amount = self._extract_number(query_lower)
                response = self._increase_volume(amount)
            elif re.search(r'\bdecrease|lower|turn\s+down|quieter\b', query_lower):
                amount = self._extract_number(query_lower)
                response = self._decrease_volume(amount)
            elif re.search(r'\bset|change\b', query_lower) or '%' in query:
                target = self._extract_percentage(query_lower)
                if target is not None:
                    response = self._set_volume(target)
                else:
                    response = "I couldn't understand the volume level. Please specify a percentage."
            else:
                # Default: get current volume
                response = self._get_current_volume()

            # Speak response
            self._speak(response, speak_response)

            return response

        except Exception as e:
            logger.error(f"Volume control failed: {e}", exc_info=True)
            error_msg = "Sorry, I couldn't control the volume."
            self._speak(error_msg, speak_response)
            return error_msg

    def _set_volume(self, percentage: int) -> str:
        """
        Set volume to specific percentage.

        Args:
            percentage: Target volume (0-100)

        Returns:
            str: Response message
        """
        try:
            # Clamp to valid range
            percentage = max(0, min(100, percentage))

            # Use pactl to set volume
            result = subprocess.run(
                ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{percentage}%'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                logger.info(f"Volume set to {percentage}%")
                return f"Volume set to {percentage} percent"
            else:
                logger.error(f"pactl failed: {result.stderr}")
                return "Failed to set volume"

        except subprocess.TimeoutExpired:
            logger.error("pactl command timed out")
            return "Volume control timed out"
        except FileNotFoundError:
            logger.error("pactl not found - PulseAudio not installed?")
            return "Volume control not available"
        except Exception as e:
            logger.error(f"Set volume failed: {e}")
            return "Failed to set volume"

    def _increase_volume(self, amount: int = 10) -> str:
        """
        Increase volume by amount.

        Args:
            amount: Amount to increase (default 10%)

        Returns:
            str: Response message
        """
        try:
            # Get current volume first
            current = self._get_current_volume_raw()
            if current is None:
                return "Failed to get current volume"

            # Calculate new volume
            new_volume = min(100, current + amount)

            return self._set_volume(new_volume)

        except Exception as e:
            logger.error(f"Increase volume failed: {e}")
            return "Failed to increase volume"

    def _decrease_volume(self, amount: int = 10) -> str:
        """
        Decrease volume by amount.

        Args:
            amount: Amount to decrease (default 10%)

        Returns:
            str: Response message
        """
        try:
            # Get current volume first
            current = self._get_current_volume_raw()
            if current is None:
                return "Failed to get current volume"

            # Calculate new volume
            new_volume = max(0, current - amount)

            return self._set_volume(new_volume)

        except Exception as e:
            logger.error(f"Decrease volume failed: {e}")
            return "Failed to decrease volume"

    def _mute(self) -> str:
        """
        Mute audio.

        Returns:
            str: Response message
        """
        try:
            result = subprocess.run(
                ['pactl', 'set-sink-mute', '@DEFAULT_SINK@', '1'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                logger.info("Audio muted")
                return "Muted"
            else:
                return "Failed to mute"

        except Exception as e:
            logger.error(f"Mute failed: {e}")
            return "Failed to mute"

    def _unmute(self) -> str:
        """
        Unmute audio.

        Returns:
            str: Response message
        """
        try:
            result = subprocess.run(
                ['pactl', 'set-sink-mute', '@DEFAULT_SINK@', '0'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                logger.info("Audio unmuted")
                return "Unmuted"
            else:
                return "Failed to unmute"

        except Exception as e:
            logger.error(f"Unmute failed: {e}")
            return "Failed to unmute"

    def _get_current_volume(self) -> str:
        """
        Get current volume as formatted string.

        Returns:
            str: Response message
        """
        volume = self._get_current_volume_raw()
        if volume is not None:
            return f"Volume is at {volume} percent"
        else:
            return "Failed to get current volume"

    def _get_current_volume_raw(self) -> Optional[int]:
        """
        Get current volume as integer.

        Returns:
            int: Volume percentage (0-100) or None if failed
        """
        try:
            result = subprocess.run(
                ['pactl', 'get-sink-volume', '@DEFAULT_SINK@'],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                # Parse output like: "Volume: front-left: 65536 / 100% / 0.00 dB, ..."
                match = re.search(r'(\d+)%', result.stdout)
                if match:
                    return int(match.group(1))

            logger.error("Failed to parse volume")
            return None

        except Exception as e:
            logger.error(f"Get volume failed: {e}")
            return None

    def _extract_percentage(self, query: str) -> Optional[int]:
        """
        Extract percentage from query.

        Args:
            query: User query

        Returns:
            int: Percentage (0-100) or None
        """
        # Look for patterns like "50%", "fifty percent", "to 75"
        match = re.search(r'(\d+)\s*%?', query)
        if match:
            return int(match.group(1))

        # Try word numbers (optional enhancement)
        return None

    def _extract_number(self, query: str) -> int:
        """
        Extract number from query.

        Args:
            query: User query

        Returns:
            int: Extracted number or default (10)
        """
        match = re.search(r'\b(\d+)\b', query)
        if match:
            return int(match.group(1))

        return 10  # Default amount
