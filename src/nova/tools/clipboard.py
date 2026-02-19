"""
Clipboard Tool - Read and write system clipboard.

Features:
- Read clipboard contents
- Write text to clipboard
- Cross-platform (uses pyperclip)
"""
import logging
from typing import Dict, Any, List

from .base import BaseTool

logger = logging.getLogger(__name__)

# Maximum clipboard content to read/write
MAX_CLIPBOARD_SIZE = 10000


class ClipboardTool(BaseTool):
    """Read and write system clipboard."""

    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def description(self) -> str:
        return (
            "Read or write the system clipboard. "
            "Actions: 'read' to get clipboard contents, 'write' to set clipboard. "
            "Useful for: copying text for the user, reading text the user copied. "
            "Examples: read clipboard, write 'Hello World' to clipboard"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "action": {
                "type": "string",
                "description": "Action to perform: 'read' or 'write'",
                "enum": ["read", "write"]
            },
            "text": {
                "type": "string",
                "description": "Text to write to clipboard (required for 'write' action)"
            }
        }

    @property
    def required_params(self) -> List[str]:
        return ["action"]

    def execute(self, **kwargs) -> str:
        """
        Read or write clipboard.

        Args:
            action: 'read' or 'write'
            text: Text to write (for write action)

        Returns:
            Clipboard contents or confirmation
        """
        action = kwargs.get("action", "").lower().strip()
        text = kwargs.get("text", "")

        if action not in ("read", "write"):
            return "ERROR: Action must be 'read' or 'write'"

        try:
            import pyperclip
        except ImportError:
            return "ERROR: pyperclip not installed. Install with: pip install pyperclip"

        if action == "read":
            return self._read_clipboard(pyperclip)
        else:
            return self._write_clipboard(pyperclip, text)

    def _read_clipboard(self, pyperclip) -> str:
        """Read clipboard contents."""
        try:
            content = pyperclip.paste()

            if not content:
                return "Clipboard is empty"

            # Truncate if too long
            if len(content) > MAX_CLIPBOARD_SIZE:
                content = content[:MAX_CLIPBOARD_SIZE]
                return f"Clipboard contents (truncated to {MAX_CLIPBOARD_SIZE} chars):\n{content}"

            logger.info(f"Read {len(content)} chars from clipboard")
            return f"Clipboard contents:\n{content}"

        except Exception as e:
            logger.error(f"Clipboard read failed: {e}")
            return f"ERROR: Failed to read clipboard - {e}"

    def _write_clipboard(self, pyperclip, text: str) -> str:
        """Write text to clipboard."""
        if not text:
            return "ERROR: No text provided for clipboard write"

        # Limit size
        if len(text) > MAX_CLIPBOARD_SIZE:
            return f"ERROR: Text too long ({len(text)} chars). Max: {MAX_CLIPBOARD_SIZE}"

        try:
            pyperclip.copy(text)
            logger.info(f"Wrote {len(text)} chars to clipboard")
            return f"Copied {len(text)} characters to clipboard"

        except Exception as e:
            logger.error(f"Clipboard write failed: {e}")
            return f"ERROR: Failed to write to clipboard - {e}"
