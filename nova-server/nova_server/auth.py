"""
Nova Auth — Token-based authentication for WebSocket connections.
"""
import hmac
import logging

logger = logging.getLogger(__name__)


class TokenAuth:
    """Pre-shared token authentication."""

    def __init__(self, expected_token: str):
        self.expected_token = expected_token

    def verify(self, token: str) -> bool:
        """Verify a token using constant-time comparison."""
        if not token or not self.expected_token:
            return False
        return hmac.compare_digest(token, self.expected_token)
