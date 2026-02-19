"""
Nova Agent — Hybrid voice bridge with local tools + Pixel Bot.

Routing logic (designed with Pixel Bot):
- Pure local (instant, no Pixel Bot): GPU stats, timer ops, notes write, time
- Hybrid (local data + Pixel Bot interpretation): clipboard, stats interpretation, notes read
- Pure remote (Pixel Bot): everything else
"""
import logging
import re
import time
from typing import Dict, Optional

from .llm import PixelBotClient, PixelBotResponse
from .tools import SystemStatsTool, ClipboardTool, TimerTool, NotesTool
from .tools.base import BaseTool

logger = logging.getLogger(__name__)

# Patterns for local tool routing
LOCAL_PATTERNS = {
    "system_stats": [
        re.compile(
            r"\b(gpu|cpu|ram|memory|disk|temp(erature)?|vram|"
            r"system\s*(stats|info|status)|processes|uptime)\b", re.I
        ),
    ],
    "clipboard": [
        re.compile(
            r"\b(clipboard|paste|copied|copy\s+to|what.*(clipboard|copied))\b", re.I
        ),
    ],
    "timer": [
        re.compile(
            r"\b(set\s*(a\s*)?timer|alarm|countdown|remind\s*me\s*in)\b", re.I
        ),
        re.compile(
            r"\b(list|check|cancel|stop)\s+(\w+\s+)*(timers?|alarms?)\b", re.I
        ),
    ],
    "notes": [
        re.compile(
            r"\b(note|notes|remember\s+that|save\s+(a\s+)?note|"
            r"my\s+notes|jot\s+down)\b", re.I
        ),
    ],
    "time": [
        re.compile(r"\bwhat\s+time\s+is\s+it\b", re.I),
        re.compile(r"\bwhat\s+day\s+is\s+it\b", re.I),
    ],
}

# Markdown patterns to strip before TTS
_MD_BOLD = re.compile(r'\*\*(.+?)\*\*')
_MD_ITALIC = re.compile(r'\*(.+?)\*')
_MD_CODE = re.compile(r'`([^`]+)`')
_MD_LINK = re.compile(r'\[([^\]]+)\]\([^\)]+\)')
_MD_HEADER = re.compile(r'^#{1,6}\s+', re.MULTILINE)
_MD_BULLET = re.compile(r'^\s*[-*]\s+', re.MULTILINE)
_MD_NUMBERED = re.compile(r'^\s*\d+\.\s+', re.MULTILINE)


def strip_markdown(text: str) -> str:
    """Strip Markdown formatting for clean TTS output."""
    text = _MD_BOLD.sub(r'\1', text)
    text = _MD_ITALIC.sub(r'\1', text)
    text = _MD_CODE.sub(r'\1', text)
    text = _MD_LINK.sub(r'\1', text)
    text = _MD_HEADER.sub('', text)
    text = _MD_BULLET.sub('', text)
    text = _MD_NUMBERED.sub('', text)
    # Collapse multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class Agent:
    """
    Nova hybrid agent — local tools + Pixel Bot bridge.

    Fast local tools handle desktop-bound queries instantly.
    Everything else goes to Pixel Bot (Claude Sonnet 4.5) via SSH.
    """

    def __init__(
        self,
        ssh_host: str = "pixel-labs-server",
        agent_name: str = "main",
        session_id: str = "nova-desktop",
        timeout: int = 15,
        max_retries: int = 1,
        retry_delay: float = 2.0,
    ):
        self.client = PixelBotClient(
            ssh_host=ssh_host,
            agent_name=agent_name,
            session_id=session_id,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        # Local tools — instant, desktop-bound
        self._tools: Dict[str, BaseTool] = {
            "system_stats": SystemStatsTool(),
            "clipboard": ClipboardTool(),
            "timer": TimerTool(),
            "notes": NotesTool(),
        }

        logger.info(
            f"Agent initialized: pixelbot={ssh_host}, "
            f"local_tools={list(self._tools.keys())}"
        )

    def chat(self, user_message: str) -> str:
        """
        Process a user message and return response.

        Routing:
        1. Pure local tools (instant) — GPU temp, timer, notes write, time
        2. Hybrid (local data + Pixel Bot) — clipboard, stats interpretation
        3. Pure remote (Pixel Bot) — everything else

        Returns text ready for TTS (Markdown stripped).
        """
        if not user_message or not user_message.strip():
            return "I didn't catch that. Could you say that again?"

        user_message = user_message.strip()
        logger.info(f"User: {user_message}")

        # Check for local tool match
        tool_name = self._match_local_tool(user_message)

        if tool_name:
            response = self._handle_local(tool_name, user_message)
        else:
            response = self._send_to_pixelbot(user_message)

        # Strip any Markdown before TTS
        return strip_markdown(response)

    def _match_local_tool(self, message: str) -> Optional[str]:
        """Match message against local tool patterns."""
        for tool_name, patterns in LOCAL_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(message):
                    logger.info(f"Local match: {tool_name}")
                    return tool_name
        return None

    def _handle_local(self, tool_name: str, user_message: str) -> str:
        """
        Handle a local tool match.

        Pure local (instant): GPU stats lookups, timer ops, notes write, time
        Hybrid (local data + Pixel Bot): clipboard, stats interpretation, notes read
        """
        msg_lower = user_message.lower()

        try:
            if tool_name == "time":
                return self._handle_time(msg_lower)

            elif tool_name == "system_stats":
                return self._handle_system_stats(msg_lower, user_message)

            elif tool_name == "clipboard":
                return self._handle_clipboard(msg_lower, user_message)

            elif tool_name == "timer":
                return self._handle_timer(msg_lower, user_message)

            elif tool_name == "notes":
                return self._handle_notes(msg_lower, user_message)

            else:
                return self._send_to_pixelbot(user_message)

        except Exception as e:
            logger.error(f"Local tool error ({tool_name}): {e}")
            return f"Sorry, I had trouble with that. {e}"

    def _handle_time(self, msg_lower: str) -> str:
        """Handle time/date queries — pure local."""
        from datetime import datetime
        now = datetime.now()
        if "day" in msg_lower:
            return now.strftime("It's %A, %B %d.")
        return now.strftime("It's %I:%M %p.")

    def _handle_system_stats(self, msg_lower: str, user_message: str) -> str:
        """
        Handle system stats queries.

        Pure lookups return instantly. Interpretation questions go hybrid.
        """
        tool = self._tools["system_stats"]

        # Determine stat type
        if "gpu" in msg_lower or "vram" in msg_lower:
            data = tool.execute(stat_type="gpu")
        elif "cpu" in msg_lower:
            data = tool.execute(stat_type="cpu")
        elif "ram" in msg_lower or "memory" in msg_lower:
            data = tool.execute(stat_type="memory")
        elif "disk" in msg_lower:
            data = tool.execute(stat_type="disk")
        elif "temp" in msg_lower:
            data = tool.execute(stat_type="temperature")
        elif "process" in msg_lower:
            data = tool.execute(stat_type="processes")
        else:
            data = tool.execute(stat_type="overview")

        # Interpretation queries go to Pixel Bot with local data
        interpretation_words = ("hot", "running", "okay", "fine", "problem",
                                "issue", "worried", "much", "enough", "low")
        if any(w in msg_lower for w in interpretation_words):
            return self._send_to_pixelbot(user_message, context=data)

        # Pure lookup — return data directly in spoken form
        return data

    def _handle_clipboard(self, msg_lower: str, user_message: str) -> str:
        """Handle clipboard queries — hybrid (local data + Pixel Bot)."""
        tool = self._tools["clipboard"]

        if any(w in msg_lower for w in ("read", "what", "show", "get", "paste",
                                         "summarize", "clipboard")):
            data = tool.execute(action="read")
            return self._send_to_pixelbot(
                user_message, context=f"Clipboard contents:\n{data}"
            )

        return self._send_to_pixelbot(user_message)

    def _handle_timer(self, msg_lower: str, user_message: str) -> str:
        """Handle timer queries — pure local."""
        tool = self._tools["timer"]

        if any(w in msg_lower for w in ("list", "check", "show", "active")):
            return tool.execute(action="list")

        if "cancel" in msg_lower or "stop" in msg_lower:
            return tool.execute(action="cancel")

        if any(w in msg_lower for w in ("set", "start", "remind")):
            duration_match = re.search(
                r'(\d+)\s*(s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?|h(?:our)?s?)',
                msg_lower
            )
            if duration_match:
                num = duration_match.group(1)
                unit = duration_match.group(2)[0]
                duration = f"{num}{unit}"
                name_match = re.search(
                    r'(?:called?|named?|for)\s+["\']?(\w+)', msg_lower
                )
                kwargs = {"action": "set", "duration": duration}
                if name_match:
                    kwargs["name"] = name_match.group(1)
                return tool.execute(**kwargs)
            return "How long should I set the timer for?"

        return tool.execute(action="list")

    def _handle_notes(self, msg_lower: str, user_message: str) -> str:
        """
        Handle notes queries.

        Write/save = pure local (instant).
        Read/search = hybrid (local data + Pixel Bot interpretation).
        """
        tool = self._tools["notes"]

        # Write operations — pure local, instant
        if any(w in msg_lower for w in ("add", "save", "remember", "jot")):
            content_match = re.search(
                r'(?:remember\s+that|save\s+(?:a\s+)?note|add\s+(?:a\s+)?note|'
                r'jot\s+down|note\s+that)\s+(.+)',
                user_message, re.I
            )
            content = content_match.group(1).strip() if content_match else user_message
            return tool.execute(action="add", content=content)

        # Read operations — hybrid
        if any(w in msg_lower for w in ("list", "show", "all notes", "read", "my notes")):
            data = tool.execute(action="list")
            return self._send_to_pixelbot(
                user_message, context=f"Notes:\n{data}"
            )

        if any(w in msg_lower for w in ("search", "find", "look for")):
            query_match = re.search(r'(?:search|find|look\s+for)\s+(.+)', msg_lower)
            query = query_match.group(1).strip() if query_match else user_message
            data = tool.execute(action="search", query=query)
            return self._send_to_pixelbot(
                user_message, context=f"Search results:\n{data}"
            )

        # Default — list
        data = tool.execute(action="list")
        return self._send_to_pixelbot(user_message, context=f"Notes:\n{data}")

    def _send_to_pixelbot(self, message: str,
                           context: Optional[str] = None) -> str:
        """Send message to Pixel Bot and return response text."""
        response = self.client.send(message, context=context)

        if response.error:
            logger.error(f"Pixel Bot error: {response.error}")
            # Error messages for TTS
            if "timed out" in response.error.lower():
                return ("Pixel Bot is taking too long. "
                        "Probably doing something heavy. I'll drop this one.")
            elif "connection" in response.error.lower() or "ssh" in response.error.lower():
                return "Can't connect to the server. Network issue or the server is offline."
            else:
                return f"I can't reach Pixel Bot right now. {response.error}"

        if not response.text:
            return "Pixel Bot didn't return a response. Try again?"

        logger.info(f"Pixel Bot ({response.latency:.1f}s): {response.text[:100]}...")
        return response.text

    def is_ready(self) -> bool:
        """Check if Pixel Bot is reachable."""
        return self.client.is_available()

    def clear_history(self):
        """No local history — Pixel Bot manages its own context."""
        logger.info("History clear (no-op, Pixel Bot manages context)")

    @property
    def tools(self) -> Dict[str, BaseTool]:
        """Get available local tools."""
        return self._tools


def create_agent(**kwargs) -> Agent:
    """Create a Nova agent with default configuration."""
    return Agent(**kwargs)
