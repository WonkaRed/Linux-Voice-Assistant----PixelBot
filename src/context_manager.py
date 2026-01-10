"""
Context Manager - Maintains separate conversation contexts for each action.

Manages:
- Transcribe context (recent transcriptions for context)
- Cortex context (conversation history for follow-up queries)
- Pixel Bot context (conversational history)

Features:
- Separate contexts per action (no cross-contamination)
- Automatic expiration after inactivity
- Configurable context size limits
"""
import logging
import time
from typing import Dict, List, Optional
from collections import deque

logger = logging.getLogger(__name__)


class ContextManager:
    """Manages separate conversation contexts for each action."""

    # Context expiration settings
    INACTIVITY_TIMEOUT = 300  # 5 minutes in seconds
    MAX_CONTEXT_LENGTH = 5  # Max conversation turns to keep

    def __init__(self):
        """Initialize context manager with separate contexts per action."""
        # Separate context storage per action
        self.contexts: Dict[str, deque] = {
            "transcribe": deque(maxlen=self.MAX_CONTEXT_LENGTH),
            "cortex": deque(maxlen=self.MAX_CONTEXT_LENGTH),
            "pixelbot": deque(maxlen=self.MAX_CONTEXT_LENGTH),
        }

        # Track last activity time per action
        self.last_activity: Dict[str, float] = {
            "transcribe": 0,
            "cortex": 0,
            "pixelbot": 0,
        }

        logger.info("ContextManager initialized")

    def add_context(self, action: str, user_text: str, processed_text: str) -> None:
        """
        Add a context entry for an action.

        Args:
            action: Action name ("transcribe", "cortex", "pixelbot")
            user_text: Original user input
            processed_text: Processed/cleaned output
        """
        if action not in self.contexts:
            logger.warning(f"Unknown action: {action}")
            return

        # Check and clear expired context
        self._check_expiration(action)

        # Add new context entry
        entry = {
            "user": user_text,
            "processed": processed_text,
            "timestamp": time.time()
        }

        self.contexts[action].append(entry)
        self.last_activity[action] = time.time()

        logger.debug(f"Context added for {action}: {len(self.contexts[action])} entries")

    def get_context(self, action: str) -> List[Dict]:
        """
        Get conversation context for an action.

        Args:
            action: Action name

        Returns:
            List of context entries (oldest to newest)
        """
        if action not in self.contexts:
            logger.warning(f"Unknown action: {action}")
            return []

        # Check and clear expired context
        self._check_expiration(action)

        return list(self.contexts[action])

    def get_context_summary(self, action: str) -> str:
        """
        Get a text summary of recent context for an action.

        Args:
            action: Action name

        Returns:
            Formatted context summary for LLM
        """
        context = self.get_context(action)

        if not context:
            return "No recent context."

        # Format context for LLM
        if action == "cortex":
            # For Cortex, show Q&A pairs
            summary_parts = []
            for i, entry in enumerate(context, 1):
                summary_parts.append(f"Q{i}: {entry['user']}")
                summary_parts.append(f"A{i}: {entry['processed']}")
            return "\n".join(summary_parts)

        elif action == "transcribe":
            # For transcribe, show recent transcriptions
            recent = [entry['processed'] for entry in context]
            return "Recent: " + " | ".join(recent[-3:])  # Last 3 only

        else:
            # Generic format
            recent = [entry['user'] for entry in context]
            return " | ".join(recent)

    def clear_context(self, action: str) -> None:
        """
        Manually clear context for an action.

        Args:
            action: Action name
        """
        if action not in self.contexts:
            return

        self.contexts[action].clear()
        self.last_activity[action] = 0
        logger.info(f"Context cleared for {action}")

    def clear_all_contexts(self) -> None:
        """Clear all contexts for all actions."""
        for action in self.contexts.keys():
            self.clear_context(action)
        logger.info("All contexts cleared")

    def _check_expiration(self, action: str) -> None:
        """
        Check and clear context if expired due to inactivity.

        Args:
            action: Action name
        """
        if action not in self.last_activity:
            return

        last_time = self.last_activity[action]

        # If never used or expired, clear context
        if last_time == 0:
            return

        elapsed = time.time() - last_time

        if elapsed > self.INACTIVITY_TIMEOUT:
            logger.info(f"Context expired for {action} ({elapsed:.0f}s > {self.INACTIVITY_TIMEOUT}s)")
            self.clear_context(action)

    def get_status(self) -> Dict:
        """
        Get status of all contexts.

        Returns:
            Status dictionary
        """
        status = {}

        for action in self.contexts.keys():
            self._check_expiration(action)

            status[action] = {
                "entries": len(self.contexts[action]),
                "last_activity": self.last_activity[action],
                "seconds_since_activity": time.time() - self.last_activity[action] if self.last_activity[action] > 0 else None,
                "expired": self.last_activity[action] > 0 and (time.time() - self.last_activity[action]) > self.INACTIVITY_TIMEOUT
            }

        return status


# Singleton instance
_context_manager = None


def get_context_manager() -> ContextManager:
    """Get or create singleton ContextManager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
