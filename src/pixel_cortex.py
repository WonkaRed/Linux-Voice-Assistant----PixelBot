"""
Pixel Cortex - Blockchain Query Assistant

Uses Moralis Cortex API for natural language blockchain queries with voice responses.

Architecture:
- Moralis Cortex API: Real-time blockchain data via natural language
- Session-based context: Maintains conversation history via chatId
- Local LLM (Qwen2.5): Optional response formatting for voice
- TTS Engine: Speaks responses back to user

Flow:
User voice → Whisper → "cortex check bitcoin price" → PixelCortex.query()
→ Moralis Cortex API → Response → (Optional LLM format) → TTS speaks
"""
import logging
import os
import uuid
from typing import Optional, Dict, Any, List

import requests

from src import config
from src.llm_manager import LLMManager
from src.tts_engine import TTSEngine

logger = logging.getLogger(__name__)


class PixelCortex:
    """
    Blockchain query assistant using Moralis Cortex API.

    Supports:
    - Natural language blockchain queries
    - Multi-turn conversations with context
    - Voice responses via TTS
    - Fallback to local LLM when API unavailable
    """

    # Moralis Cortex API endpoint
    CORTEX_API_URL = "https://cortex-api.moralis.io/chat"

    # Response formatting thresholds
    MAX_VOICE_WORDS = 50  # Responses longer than this get condensed
    API_TIMEOUT = 30  # seconds (Moralis can be slow for complex queries)

    def __init__(self, llm_manager: LLMManager, tts_engine: Optional[TTSEngine] = None):
        """
        Initialize Pixel Cortex.

        Args:
            llm_manager: LLM manager instance (for fallback and formatting)
            tts_engine: Optional TTS engine for voice responses
        """
        self.llm = llm_manager
        self.tts = tts_engine
        self.moralis_api_key = os.getenv("MORALIS_API_KEY")
        self.is_available = bool(self.moralis_api_key)

        # Session-based conversation context
        self.session_id = str(uuid.uuid4())
        self.conversation_history: List[Dict[str, str]] = []

        if not self.is_available:
            logger.warning("MORALIS_API_KEY not found in .env - Cortex will use local LLM fallback")
        else:
            logger.info(f"Pixel Cortex initialized (session: {self.session_id[:8]}...)")
            logger.info(f"  Cortex API: Available")
            logger.info(f"  TTS: {'Available' if tts_engine and tts_engine.is_available else 'Disabled'}")

    def query(self, user_query: str, speak_response: bool = True) -> str:
        """
        Process blockchain query using Moralis Cortex API.

        Args:
            user_query: Natural language blockchain query
            speak_response: Whether to speak the response via TTS

        Returns:
            str: Response text

        Examples:
            >>> cortex.query("What is the price of Bitcoin?")
            "Bitcoin is currently trading at $65,000"

            >>> cortex.query("Check Ethereum balance for vitalik.eth")
            "The address has 1,234 ETH valued at $4.2M"
        """
        if not user_query or not user_query.strip():
            logger.warning("Empty query provided to Cortex")
            return ""

        try:
            logger.info(f"Cortex query: '{user_query[:100]}'")

            # Try Moralis Cortex API first
            if self.is_available:
                try:
                    response = self._query_cortex_api(user_query)
                    logger.info("✓ Cortex API response received")
                except Exception as api_error:
                    logger.warning(f"Cortex API failed, using LLM fallback: {api_error}")
                    # Use fallback with error context
                    response = self._fallback_llm_query(user_query, api_error=str(api_error))
            else:
                # No API key, use local LLM
                logger.info("Using local LLM fallback (no API key)")
                response = self._fallback_llm_query(user_query, no_api_key=True)

            # Format for voice if needed
            if speak_response:
                voice_response = self._format_for_voice(response)
                logger.info(f"Cortex response ({len(response.split())} words): '{response[:100]}'")
                logger.info(f"Voice response ({len(voice_response.split())} words): '{voice_response[:100]}'")
            else:
                voice_response = response

            # Speak response if TTS available and requested
            if speak_response and self.tts and self.tts.is_available:
                logger.info("Speaking response via TTS...")
                self.tts.speak_async(voice_response)

            return response

        except Exception as e:
            logger.error(f"Cortex query failed: {e}", exc_info=True)
            error_msg = "Sorry, I encountered an error processing your blockchain query."

            if speak_response and self.tts and self.tts.is_available:
                self.tts.speak_async(error_msg)

            return error_msg

    def _query_cortex_api(self, query: str) -> str:
        """
        Query Moralis Cortex API with conversation context.

        Args:
            query: Natural language blockchain query

        Returns:
            str: Cortex API response

        Raises:
            Exception: If API call fails

        Note:
            Moralis Cortex API format:
            - Request: {"prompt": "query text", "chatId": "session-id"}
            - Response: {"text": "response text"}
            - chatId is REQUIRED (500 error without it)
        """
        # Prepare API request
        headers = {
            "X-API-Key": self.moralis_api_key,
            "Content-Type": "application/json",
        }

        # Moralis Cortex uses simple prompt + chatId format
        payload = {
            "prompt": query,
            "chatId": self.session_id  # Required for conversation context
        }

        logger.debug(f"Cortex API request - Session: {self.session_id[:8]}...")

        # Call Cortex API with retry logic
        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.debug(f"Cortex API request attempt {attempt + 1}/{max_retries}")

                response = requests.post(
                    self.CORTEX_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.API_TIMEOUT
                )

                # Log the response for debugging
                logger.debug(f"Cortex API status: {response.status_code}")

                response.raise_for_status()
                data = response.json()

                # Success - break out of retry loop
                break

            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Cortex API timeout, retrying... ({attempt + 1}/{max_retries})")
                    continue
                else:
                    logger.error(f"Cortex API timeout after {max_retries} attempts")
                    raise

            except requests.exceptions.HTTPError as e:
                # Log detailed error for debugging
                logger.error(f"Cortex API HTTP error: {e}")
                logger.error(f"Response body: {response.text if response else 'No response'}")

                # Don't retry on 4xx errors (client errors)
                if response.status_code < 500:
                    raise

                # Retry on 5xx errors (server errors)
                if attempt < max_retries - 1:
                    logger.warning(f"Cortex API server error, retrying... ({attempt + 1}/{max_retries})")
                    continue
                else:
                    raise

            except requests.exceptions.RequestException as e:
                logger.error(f"Cortex API request error: {e}")

                if attempt < max_retries - 1:
                    logger.warning(f"Cortex API error, retrying... ({attempt + 1}/{max_retries})")
                    continue
                else:
                    raise

        # Extract response text from Moralis Cortex format
        if isinstance(data, dict) and "text" in data:
            cortex_response = data["text"]
        else:
            # Fallback if format changes
            cortex_response = data.get("response", data.get("message", str(data)))

        # Track conversation locally for context awareness
        self.conversation_history.append({"query": query, "response": cortex_response})

        # Limit conversation history to last 5 exchanges
        if len(self.conversation_history) > 5:
            self.conversation_history = self.conversation_history[-5:]

        return cortex_response

    def _fallback_llm_query(self, query: str, no_api_key: bool = False, api_error: str = None) -> str:
        """
        Fallback to local LLM when Cortex API unavailable.

        Args:
            query: Natural language blockchain query
            no_api_key: True if API key is missing
            api_error: Error message from API if it failed

        Returns:
            str: LLM response
        """
        try:
            # Use local Qwen2.5 for general blockchain knowledge
            if no_api_key:
                # No API key configured
                prompt = f"""You are Pixel Cortex, a blockchain knowledge assistant.

Answer this blockchain question concisely in 1-2 sentences.
If the question requires real-time data (prices, balances, transactions), explain that you need a Moralis API key for that.

Question: {query}

Answer:"""
            elif api_error:
                # API error/timeout - provide best effort answer
                prompt = f"""You are Pixel Cortex, a blockchain knowledge assistant.

The real-time API is temporarily unavailable. Provide a helpful answer using your general knowledge.
If you can answer conceptually, do so. If you need live data, acknowledge the limitation briefly.

Question: {query}

Answer:"""
            else:
                # General fallback
                prompt = f"""You are Pixel Cortex, a blockchain knowledge assistant.

Answer this blockchain question concisely in 1-2 sentences.

Question: {query}

Answer:"""

            messages = [{"role": "user", "content": prompt}]
            response = self.llm.generate(
                messages,
                max_tokens=150,
                temperature=0.7
            )

            return response.strip()

        except Exception as e:
            logger.error(f"LLM fallback failed: {e}")
            return "I'm having trouble answering that question right now. Please try again."

    def _format_for_voice(self, response: str) -> str:
        """
        Format response for voice output.

        Long responses are condensed using local LLM.
        Short responses are passed through unchanged.

        Args:
            response: Original response text

        Returns:
            str: Voice-optimized response
        """
        word_count = len(response.split())

        # If response is short, use as-is
        if word_count <= self.MAX_VOICE_WORDS:
            return response

        # Long response - condense with LLM
        try:
            logger.info(f"Condensing {word_count}-word response for voice...")

            prompt = f"""Condense this blockchain information for voice output.

Keep it under 50 words while preserving key facts. Be conversational and concise.

Original: {response}

Condensed:"""

            messages = [{"role": "user", "content": prompt}]
            condensed = self.llm.generate(
                messages,
                max_tokens=100,
                temperature=0.3
            )

            return condensed.strip()

        except Exception as e:
            logger.error(f"Response formatting failed: {e}")
            # Fallback: truncate to first 2 sentences
            sentences = response.split('.')[:2]
            return '. '.join(sentences) + '.'

    def reset_conversation(self) -> None:
        """
        Reset conversation context and start a new session.

        Useful for:
        - Starting fresh topic
        - Clearing context after errors
        - Privacy (clearing conversation history)
        """
        old_session = self.session_id[:8]
        self.session_id = str(uuid.uuid4())
        self.conversation_history = []
        logger.info(f"Conversation reset: {old_session}... → {self.session_id[:8]}...")

    def get_status(self) -> dict:
        """
        Get Cortex status.

        Returns:
            dict: Status information including API availability, session info, and context state
        """
        return {
            "available": self.is_available,
            "api_key_set": bool(self.moralis_api_key),
            "llm_ready": self.llm.is_loaded if self.llm else False,
            "tts_available": self.tts.is_available if self.tts else False,
            "session_id": self.session_id[:8] + "...",
            "conversation_length": len(self.conversation_history),
        }


# Test function
def test_pixel_cortex():
    """Test Pixel Cortex with Moralis API or LLM fallback."""
    print("\n" + "=" * 80)
    print("PIXEL CORTEX TEST - Moralis Cortex API Integration")
    print("=" * 80)

    # Load environment
    from dotenv import load_dotenv
    load_dotenv()

    # Initialize LLM
    print("\n[1/4] Initializing LLM...")
    from src.llm_manager import LLMManager
    llm = LLMManager()

    if not llm.load():
        print("❌ Failed to load LLM")
        return False

    print(f"✓ LLM loaded ({llm.vram_usage:.2f}GB VRAM)")

    # Initialize TTS (optional)
    print("\n[2/4] Initializing TTS (optional)...")
    from src.tts_engine import TTSEngine
    tts = TTSEngine()

    if tts.is_available:
        print("✓ TTS available (OpenAI API key found)")
    else:
        print("⚠️  TTS unavailable (no OpenAI API key)")

    # Create Cortex
    print("\n[3/4] Creating Pixel Cortex...")
    cortex = PixelCortex(llm, tts)
    status = cortex.get_status()

    print(f"\nStatus:")
    print(f"  Cortex API: {'✓ Available' if status['available'] else '✗ Unavailable (no MORALIS_API_KEY)'}")
    print(f"  LLM Fallback: {'✓ Ready' if status['llm_ready'] else '✗ Not ready'}")
    print(f"  TTS: {'✓ Available' if status['tts_available'] else '✗ Disabled'}")
    print(f"  Session: {status['session_id']}")
    print(f"  History: {status['conversation_length']} messages")

    # Test queries
    print("\n[4/4] Testing blockchain queries...")
    print("=" * 80)

    test_queries = [
        ("What is blockchain?", "General knowledge test"),
        ("What is the price of Bitcoin?", "Real-time data test (requires API)"),
        ("Explain DeFi in simple terms", "Conceptual explanation test"),
    ]

    for i, (query, description) in enumerate(test_queries, 1):
        print(f"\nTest {i}: {description}")
        print(f"Query: '{query}'")
        print("-" * 80)

        # Query without TTS for testing
        response = cortex.query(query, speak_response=False)

        print(f"Response: '{response}'")
        print(f"Words: {len(response.split())}")

    # Test context (multi-turn conversation)
    print("\n" + "=" * 80)
    print("CONTEXT TEST - Multi-turn Conversation")
    print("=" * 80)

    print("\nQuery 1: 'What is Ethereum?'")
    response1 = cortex.query("What is Ethereum?", speak_response=False)
    print(f"Response: '{response1[:100]}...'")

    print("\nQuery 2: 'What's its market cap?' (uses context)")
    response2 = cortex.query("What's its market cap?", speak_response=False)
    print(f"Response: '{response2[:100]}...'")

    print(f"\nConversation history: {len(cortex.conversation_history)} messages")

    # Test reset
    print("\n" + "=" * 80)
    print("Testing conversation reset...")
    cortex.reset_conversation()
    print(f"✓ Conversation reset. History: {len(cortex.conversation_history)} messages")

    # Cleanup
    print("\n" + "=" * 80)
    print("Cleanup...")
    llm.unload()
    print("✓ LLM unloaded")

    print("\n" + "=" * 80)
    print("✅ PIXEL CORTEX TEST COMPLETE")
    print("=" * 80)

    print("\nNext steps:")
    if not status['available']:
        print("  1. Add MORALIS_API_KEY to .env file")
        print("  2. Get your API key from https://admin.moralis.io")
    if not status['tts_available']:
        print("  3. Add OPENAI_API_KEY to .env for voice responses")
    print("  4. Test with voice: Run dictation_daemon.py")
    print("  5. Say: 'cortex, what is Bitcoin?'")

    return True


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run test
    import sys
    success = test_pixel_cortex()
    sys.exit(0 if success else 1)
