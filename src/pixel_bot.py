"""
Pixel Bot - Conversational AI Assistant

Uses local Phi-3-mini LLM for chat-based interactions.
Provides voice-based Q&A and general assistance.
"""
import logging
from typing import List, Dict, Optional

from src import config
from src.llm_manager import LLMManager
from src.tts_engine import TTSEngine

logger = logging.getLogger(__name__)


class PixelBot:
    """Conversational AI assistant using local LLM."""

    def __init__(self, llm_manager: LLMManager, tts_engine: Optional[TTSEngine] = None):
        """
        Initialize Pixel Bot.

        Args:
            llm_manager: LLM manager instance
            tts_engine: Optional TTS engine for voice responses
        """
        self.llm = llm_manager
        self.tts = tts_engine
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 10  # Keep last 10 exchanges

        logger.info("PixelBot initialized")

    def chat(self, user_message: str, speak_response: bool = True) -> str:
        """
        Chat with Pixel Bot.

        Args:
            user_message: User's message/question
            speak_response: Whether to speak the response via TTS

        Returns:
            str: Bot's response
        """
        if not user_message or not user_message.strip():
            logger.warning("Empty message provided to Pixel Bot")
            return ""

        try:
            logger.info(f"Pixel Bot query: '{user_message[:100]}'")

            # Add to conversation history
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })

            # Trim history if too long
            if len(self.conversation_history) > self.max_history * 2:
                # Keep only last max_history exchanges (each exchange = 2 messages)
                self.conversation_history = self.conversation_history[-(self.max_history * 2):]

            # Generate response using LLM
            response = self.llm.chat(
                user_message,
                conversation_history=self.conversation_history[:-1],  # Exclude current message
                system_prompt=config.PIXEL_BOT_SYSTEM_PROMPT,
            )

            # Add response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response
            })

            logger.info(f"Pixel Bot response: '{response[:100]}'")

            # Speak response if TTS available and requested
            if speak_response and self.tts and self.tts.is_available:
                self.tts.speak_async(response, voice="nova")

            return response

        except Exception as e:
            logger.error(f"Pixel Bot chat failed: {e}", exc_info=True)
            error_msg = "Sorry, I encountered an error processing your request."

            if speak_response and self.tts and self.tts.is_available:
                self.tts.speak_async(error_msg, voice="nova")

            return error_msg

    def reset_conversation(self):
        """Clear conversation history."""
        self.conversation_history = []
        logger.info("Conversation history cleared")

    def get_conversation_length(self) -> int:
        """Get number of exchanges in current conversation."""
        return len(self.conversation_history) // 2

    def get_status(self) -> dict:
        """
        Get Pixel Bot status.

        Returns:
            dict: Status information
        """
        return {
            "conversation_length": self.get_conversation_length(),
            "max_history": self.max_history,
            "llm_ready": self.llm.is_loaded if self.llm else False,
            "tts_available": self.tts.is_available if self.tts else False,
        }


# Test function
def test_pixel_bot():
    """Test Pixel Bot with local LLM."""
    print("\n" + "=" * 70)
    print("PIXEL BOT TEST (Local LLM)")
    print("=" * 70)

    # Initialize LLM
    print("\n1. Initializing LLM (Phi-3-mini)...")
    print("   This may take 30-60 seconds...")

    from src.llm_manager import LLMManager
    llm = LLMManager()

    if not llm.load():
        print("❌ Failed to load LLM")
        return False

    print("   ✓ LLM loaded")

    # Initialize TTS (optional)
    print("\n2. Initializing TTS (optional)...")
    from src.tts_engine import TTSEngine
    from dotenv import load_dotenv
    load_dotenv()

    tts = TTSEngine()

    if tts.is_available:
        print("   ✓ TTS available")
    else:
        print("   ⚠️  TTS not available (responses won't be spoken)")

    # Create Pixel Bot
    print("\n3. Creating Pixel Bot...")
    bot = PixelBot(llm, tts)
    print(f"   ✓ Pixel Bot ready")
    print(f"   Status: {bot.get_status()}")

    # Test conversations
    print("\n4. Testing conversations...")

    test_queries = [
        "What is 2 plus 2?",
        "Tell me a short fun fact about Python programming",
        "What's the capital of France?",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n   Query {i}: '{query}'")
        response = bot.chat(query, speak_response=False)  # Don't speak in test
        print(f"   Response: '{response}'")
        print(f"   Conversation length: {bot.get_conversation_length()} exchanges")

    # Test conversation reset
    print("\n5. Testing conversation reset...")
    bot.reset_conversation()
    print(f"   ✓ Conversation cleared")
    print(f"   Conversation length: {bot.get_conversation_length()} exchanges")

    # Cleanup
    print("\n6. Shutting down...")
    llm.unload()
    print("   ✓ LLM unloaded")

    print("\n" + "=" * 70)
    print("✅ PIXEL BOT TEST COMPLETE")
    print("=" * 70)

    return True


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run test
    import sys
    success = test_pixel_bot()
    sys.exit(0 if success else 1)
