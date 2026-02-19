"""
Nova Tools - Local desktop-bound tools.

Available tools:
- system_stats: Get system information (CPU, RAM, GPU, etc.)
- clipboard: Read and write system clipboard
- timer: Set and manage multiple named timers
- notes: Quick note-taking with organized storage
"""

from .base import BaseTool
from .system_stats import SystemStatsTool
from .clipboard import ClipboardTool
from .timer import TimerTool
from .notes import NotesTool

__all__ = [
    "BaseTool",
    "SystemStatsTool",
    "ClipboardTool",
    "TimerTool",
    "NotesTool",
]
