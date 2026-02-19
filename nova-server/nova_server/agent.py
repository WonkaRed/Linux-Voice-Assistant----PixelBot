"""
Nova Server Agent — Routing logic with local tools executed on desktop node.

Routing:
- Pure local (instant, no Pixel Bot): time queries
- Tool request (execute on node): GPU stats, timer, notes, clipboard
- Hybrid (node tool data + Pixel Bot): stats interpretation, clipboard read, notes read
- Pure remote (Pixel Bot): everything else
"""
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, Optional

from .pixelbot import PixelBotClient, PixelBotResponse

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
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# Type for the callback that requests tool execution on the node
ToolRequestFunc = Callable[[str, Dict[str, Any]], Coroutine[Any, Any, str]]


class ServerAgent:
    """
    Nova server-side agent — routes queries, executes via node or Pixel Bot.

    Tools are executed remotely on the desktop node via WebSocket.
    """

    def __init__(self, pixelbot: PixelBotClient, request_tool: ToolRequestFunc):
        """
        Args:
            pixelbot: Pixel Bot client for LLM queries
            request_tool: Async callback to request tool execution on node.
                          Signature: async (tool_name, params) -> result_str
        """
        self.pixelbot = pixelbot
        self.request_tool = request_tool
        logger.info("ServerAgent initialized")

    async def chat(self, user_message: str) -> str:
        """
        Process a user message and return TTS-ready response.

        Routes through local patterns, then to Pixel Bot for everything else.
        """
        if not user_message or not user_message.strip():
            return "I didn't catch that. Could you say that again?"

        user_message = user_message.strip()
        logger.info(f"User: {user_message}")

        tool_name = self._match_local_tool(user_message)

        if tool_name:
            response = await self._handle_local(tool_name, user_message)
        else:
            response = await self._send_to_pixelbot(user_message)

        return strip_markdown(response)

    def _match_local_tool(self, message: str) -> Optional[str]:
        """Match message against local tool patterns."""
        for tool_name, patterns in LOCAL_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(message):
                    logger.info(f"Local match: {tool_name}")
                    return tool_name
        return None

    async def _handle_local(self, tool_name: str, user_message: str) -> str:
        """Handle a local tool match by requesting execution from the node."""
        msg_lower = user_message.lower()

        try:
            if tool_name == "time":
                return self._handle_time(msg_lower)

            elif tool_name == "system_stats":
                return await self._handle_system_stats(msg_lower, user_message)

            elif tool_name == "clipboard":
                return await self._handle_clipboard(msg_lower, user_message)

            elif tool_name == "timer":
                return await self._handle_timer(msg_lower, user_message)

            elif tool_name == "notes":
                return await self._handle_notes(msg_lower, user_message)

            else:
                return await self._send_to_pixelbot(user_message)

        except Exception as e:
            logger.error(f"Local tool error ({tool_name}): {e}")
            return f"Sorry, I had trouble with that. {e}"

    def _handle_time(self, msg_lower: str) -> str:
        """Handle time/date queries — pure server-side."""
        now = datetime.now()
        if "day" in msg_lower:
            return now.strftime("It's %A, %B %d.")
        return now.strftime("It's %I:%M %p.")

    async def _handle_system_stats(self, msg_lower: str, user_message: str) -> str:
        """Handle system stats — request from node, optionally interpret via Pixel Bot."""
        if "gpu" in msg_lower or "vram" in msg_lower:
            data = await self.request_tool("system_stats", {"stat_type": "gpu"})
        elif "cpu" in msg_lower:
            data = await self.request_tool("system_stats", {"stat_type": "cpu"})
        elif "ram" in msg_lower or "memory" in msg_lower:
            data = await self.request_tool("system_stats", {"stat_type": "memory"})
        elif "disk" in msg_lower:
            data = await self.request_tool("system_stats", {"stat_type": "disk"})
        elif "temp" in msg_lower:
            data = await self.request_tool("system_stats", {"stat_type": "temperature"})
        elif "process" in msg_lower:
            data = await self.request_tool("system_stats", {"stat_type": "processes"})
        else:
            data = await self.request_tool("system_stats", {"stat_type": "overview"})

        # Interpretation queries go to Pixel Bot with local data
        interpretation_words = ("hot", "running", "okay", "fine", "problem",
                                "issue", "worried", "much", "enough", "low")
        if any(w in msg_lower for w in interpretation_words):
            return await self._send_to_pixelbot(user_message, context=data)

        return data

    async def _handle_clipboard(self, msg_lower: str, user_message: str) -> str:
        """Handle clipboard — hybrid (node data + Pixel Bot)."""
        if any(w in msg_lower for w in ("read", "what", "show", "get", "paste",
                                         "summarize", "clipboard")):
            data = await self.request_tool("clipboard", {"action": "read"})
            return await self._send_to_pixelbot(
                user_message, context=f"Clipboard contents:\n{data}"
            )
        return await self._send_to_pixelbot(user_message)

    async def _handle_timer(self, msg_lower: str, user_message: str) -> str:
        """Handle timer queries — execute on node."""
        if any(w in msg_lower for w in ("list", "check", "show", "active")):
            return await self.request_tool("timer", {"action": "list"})

        if "cancel" in msg_lower or "stop" in msg_lower:
            return await self.request_tool("timer", {"action": "cancel"})

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
                params = {"action": "set", "duration": duration}
                if name_match:
                    params["name"] = name_match.group(1)
                return await self.request_tool("timer", params)
            return "How long should I set the timer for?"

        return await self.request_tool("timer", {"action": "list"})

    async def _handle_notes(self, msg_lower: str, user_message: str) -> str:
        """Handle notes — write is pure node, read is hybrid."""
        if any(w in msg_lower for w in ("add", "save", "remember", "jot")):
            content_match = re.search(
                r'(?:remember\s+that|save\s+(?:a\s+)?note|add\s+(?:a\s+)?note|'
                r'jot\s+down|note\s+that)\s+(.+)',
                user_message, re.I
            )
            content = content_match.group(1).strip() if content_match else user_message
            return await self.request_tool("notes", {"action": "add", "content": content})

        if any(w in msg_lower for w in ("list", "show", "all notes", "read", "my notes")):
            data = await self.request_tool("notes", {"action": "list"})
            return await self._send_to_pixelbot(
                user_message, context=f"Notes:\n{data}"
            )

        if any(w in msg_lower for w in ("search", "find", "look for")):
            query_match = re.search(r'(?:search|find|look\s+for)\s+(.+)', msg_lower)
            query = query_match.group(1).strip() if query_match else user_message
            data = await self.request_tool("notes", {"action": "search", "query": query})
            return await self._send_to_pixelbot(
                user_message, context=f"Search results:\n{data}"
            )

        data = await self.request_tool("notes", {"action": "list"})
        return await self._send_to_pixelbot(user_message, context=f"Notes:\n{data}")

    async def _send_to_pixelbot(self, message: str,
                                 context: Optional[str] = None) -> str:
        """Send message to Pixel Bot (runs in thread pool to avoid blocking)."""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self.pixelbot.send(message, context=context)
        )

        if response.error:
            logger.error(f"Pixel Bot error: {response.error}")
            if "timed out" in response.error.lower():
                return ("Pixel Bot is taking too long. "
                        "Probably doing something heavy. I'll drop this one.")
            elif "connection" in response.error.lower():
                return "Can't reach Pixel Bot right now. Check if OpenClaw is running."
            else:
                return f"I can't reach Pixel Bot right now. {response.error}"

        if not response.text:
            return "Pixel Bot didn't return a response. Try again?"

        logger.info(f"Pixel Bot ({response.latency:.1f}s): {response.text[:100]}...")
        return response.text
