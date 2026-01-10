"""
Base Handler - Abstract base class for all Pixel Bot handlers.
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional

from src.llm_manager import LLMManager
from src.tts_engine import TTSEngine

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """
    Abstract base class for all handlers.

    Handlers implement specific functionality (volume, stats, apps, etc.)
    All handlers follow the same pattern:
    1. Parse query (extract parameters)
    2. Execute action (system command, calculation, etc.)
    3. Format response (LLM makes it natural)
    4. Speak response (TTS if available)
    """

    def __init__(self, llm_manager: LLMManager, tts_engine: Optional[TTSEngine] = None):
        """
        Initialize handler.

        Args:
            llm_manager: LLM for natural language processing
            tts_engine: Optional TTS for voice responses
        """
        self.llm = llm_manager
        self.tts = tts_engine
        self.name = self.__class__.__name__

    @abstractmethod
    def handle(self, query: str, speak_response: bool = True) -> str:
        """
        Handle a user query.

        Args:
            query: User's query
            speak_response: Whether to speak the response

        Returns:
            str: Response text
        """
        pass

    def _speak(self, text: str, speak_enabled: bool = True):
        """
        Speak text if TTS available and enabled.

        Args:
            text: Text to speak
            speak_enabled: Whether speaking is enabled
        """
        if speak_enabled and self.tts and self.tts.is_available:
            self.tts.speak_async(text)

    def _format_response(self, raw_data: str, context: str = "") -> str:
        """
        Format raw data into natural language response.

        Uses LLM to make responses sound conversational.

        Args:
            raw_data: Raw data to format
            context: Optional context for formatting

        Returns:
            str: Formatted natural language response
        """
        try:
            prompt = f"""Format this information into a natural, conversational response.
Keep it SHORT (under 15 words) and friendly.
{context}

Information: {raw_data}
Response:"""

            messages = [{"role": "user", "content": prompt}]
            response = self.llm.generate(
                messages,
                max_tokens=50,
                temperature=0.3
            ).strip()

            # Clean up common LLM artifacts
            response = response.strip('"\'')
            if response.lower().startswith('response:'):
                response = response[9:].strip()

            return response

        except Exception as e:
            logger.error(f"Response formatting failed: {e}")
            # Fallback: return raw data
            return raw_data
