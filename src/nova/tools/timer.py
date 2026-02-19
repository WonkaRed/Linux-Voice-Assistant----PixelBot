"""
Timer Tool - Set and manage multiple named timers.

Features:
- Multiple concurrent timers
- Named timers for identification
- Desktop notifications when timers complete
- List, cancel, check remaining time
"""
import logging
import threading
import time
import subprocess
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from .base import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class Timer:
    """Represents an active timer."""
    name: str
    duration_seconds: int
    start_time: float
    end_time: float
    thread: threading.Thread
    cancelled: bool = False


class TimerTool(BaseTool):
    """Manage multiple named timers with notifications."""

    # Class-level timer storage (persists across instances)
    _timers: Dict[str, Timer] = {}
    _lock = threading.Lock()
    _counter = 0

    @property
    def name(self) -> str:
        return "timer"

    @property
    def description(self) -> str:
        return (
            "Set, list, or cancel timers. Supports multiple named timers. "
            "Actions: 'set' (create timer), 'list' (show active), 'cancel' (stop timer), 'check' (time remaining). "
            "Duration: specify in seconds, minutes (m), or hours (h). "
            "Examples: 'set 5m', 'set 30 seconds', 'set 1h named cooking', 'list', 'cancel cooking'"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "action": {
                "type": "string",
                "description": "Action: 'set', 'list', 'cancel', or 'check'",
                "enum": ["set", "list", "cancel", "check"]
            },
            "duration": {
                "type": "string",
                "description": "Timer duration (e.g., '5m', '30', '1h', '90s')"
            },
            "timer_name": {
                "type": "string",
                "description": "Name for the timer (optional, auto-generated if not provided)"
            }
        }

    @property
    def required_params(self) -> List[str]:
        return ["action"]

    def execute(self, **kwargs) -> str:
        """
        Execute timer action.

        Args:
            action: set, list, cancel, or check
            duration: Time duration for 'set' action
            timer_name: Name of timer

        Returns:
            Result message
        """
        action = kwargs.get("action", "").lower().strip()
        duration = kwargs.get("duration", "")
        timer_name = kwargs.get("timer_name", "").strip()

        if action == "set":
            return self._set_timer(duration, timer_name)
        elif action == "list":
            return self._list_timers()
        elif action == "cancel":
            return self._cancel_timer(timer_name)
        elif action == "check":
            return self._check_timer(timer_name)
        else:
            return "ERROR: Action must be 'set', 'list', 'cancel', or 'check'"

    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse duration string to seconds."""
        if not duration_str:
            return None

        duration_str = duration_str.lower().strip()

        try:
            # Try parsing as plain number (assume seconds)
            if duration_str.isdigit():
                return int(duration_str)

            # Parse with unit
            if duration_str.endswith('h'):
                return int(float(duration_str[:-1]) * 3600)
            elif duration_str.endswith('m'):
                return int(float(duration_str[:-1]) * 60)
            elif duration_str.endswith('s'):
                return int(float(duration_str[:-1]))
            elif 'hour' in duration_str:
                num = ''.join(c for c in duration_str if c.isdigit() or c == '.')
                return int(float(num) * 3600) if num else None
            elif 'minute' in duration_str:
                num = ''.join(c for c in duration_str if c.isdigit() or c == '.')
                return int(float(num) * 60) if num else None
            elif 'second' in duration_str:
                num = ''.join(c for c in duration_str if c.isdigit() or c == '.')
                return int(float(num)) if num else None
            else:
                # Try parsing as float
                return int(float(duration_str))

        except (ValueError, TypeError):
            return None

    def _set_timer(self, duration: str, timer_name: str) -> str:
        """Set a new timer."""
        seconds = self._parse_duration(duration)

        if seconds is None or seconds <= 0:
            return f"ERROR: Invalid duration '{duration}'. Use format: '5m', '30s', '1h', or just seconds"

        if seconds > 86400:  # 24 hours max
            return "ERROR: Timer cannot exceed 24 hours"

        # Generate name if not provided
        with self._lock:
            if not timer_name:
                TimerTool._counter += 1
                timer_name = f"timer-{TimerTool._counter}"

            # Check for duplicate name
            if timer_name in TimerTool._timers:
                return f"ERROR: Timer '{timer_name}' already exists. Cancel it first or use a different name."

            # Create timer
            start_time = time.time()
            end_time = start_time + seconds

            # Create thread
            thread = threading.Thread(
                target=self._timer_thread,
                args=(timer_name, seconds),
                daemon=True
            )

            timer = Timer(
                name=timer_name,
                duration_seconds=seconds,
                start_time=start_time,
                end_time=end_time,
                thread=thread
            )

            TimerTool._timers[timer_name] = timer
            thread.start()

        # Format duration for response
        if seconds >= 3600:
            dur_str = f"{seconds // 3600}h {(seconds % 3600) // 60}m"
        elif seconds >= 60:
            dur_str = f"{seconds // 60}m {seconds % 60}s"
        else:
            dur_str = f"{seconds}s"

        logger.info(f"Timer '{timer_name}' set for {dur_str}")
        return f"Timer '{timer_name}' set for {dur_str}"

    def _timer_thread(self, timer_name: str, seconds: int):
        """Timer thread that waits and notifies."""
        # Sleep in small intervals to allow cancellation
        end_time = time.time() + seconds
        while time.time() < end_time:
            time.sleep(0.5)

            with self._lock:
                timer = TimerTool._timers.get(timer_name)
                if not timer or timer.cancelled:
                    return

        # Timer completed
        with self._lock:
            timer = TimerTool._timers.get(timer_name)
            if timer and not timer.cancelled:
                del TimerTool._timers[timer_name]

        # Send notification
        self._notify(timer_name)

    def _notify(self, timer_name: str):
        """Send desktop notification for completed timer."""
        logger.info(f"Timer '{timer_name}' completed!")
        try:
            subprocess.Popen(
                ["notify-send", "-u", "critical", "-t", "10000",
                 "Timer Complete", f"Timer '{timer_name}' has finished!"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Also try to play a sound
            subprocess.Popen(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except:
            pass

    def _list_timers(self) -> str:
        """List all active timers."""
        with self._lock:
            if not TimerTool._timers:
                return "No active timers"

            lines = ["Active timers:"]
            now = time.time()

            for name, timer in TimerTool._timers.items():
                remaining = max(0, timer.end_time - now)
                if remaining >= 3600:
                    rem_str = f"{int(remaining // 3600)}h {int((remaining % 3600) // 60)}m"
                elif remaining >= 60:
                    rem_str = f"{int(remaining // 60)}m {int(remaining % 60)}s"
                else:
                    rem_str = f"{int(remaining)}s"

                lines.append(f"  - {name}: {rem_str} remaining")

            return "\n".join(lines)

    def _cancel_timer(self, timer_name: str) -> str:
        """Cancel a timer by name."""
        if not timer_name:
            return "ERROR: Please specify timer name to cancel"

        with self._lock:
            timer = TimerTool._timers.get(timer_name)
            if not timer:
                # Try partial match
                matches = [n for n in TimerTool._timers.keys() if timer_name.lower() in n.lower()]
                if len(matches) == 1:
                    timer_name = matches[0]
                    timer = TimerTool._timers[timer_name]
                elif len(matches) > 1:
                    return f"ERROR: Multiple timers match '{timer_name}': {', '.join(matches)}"
                else:
                    return f"ERROR: Timer '{timer_name}' not found"

            timer.cancelled = True
            del TimerTool._timers[timer_name]

        logger.info(f"Timer '{timer_name}' cancelled")
        return f"Timer '{timer_name}' cancelled"

    def _check_timer(self, timer_name: str) -> str:
        """Check remaining time on a timer."""
        if not timer_name:
            # If only one timer, check it
            with self._lock:
                if len(TimerTool._timers) == 1:
                    timer_name = list(TimerTool._timers.keys())[0]
                elif len(TimerTool._timers) == 0:
                    return "No active timers"
                else:
                    return self._list_timers()

        with self._lock:
            timer = TimerTool._timers.get(timer_name)
            if not timer:
                return f"ERROR: Timer '{timer_name}' not found"

            remaining = max(0, timer.end_time - time.time())
            if remaining >= 3600:
                rem_str = f"{int(remaining // 3600)} hours {int((remaining % 3600) // 60)} minutes"
            elif remaining >= 60:
                rem_str = f"{int(remaining // 60)} minutes {int(remaining % 60)} seconds"
            else:
                rem_str = f"{int(remaining)} seconds"

            return f"Timer '{timer_name}': {rem_str} remaining"
