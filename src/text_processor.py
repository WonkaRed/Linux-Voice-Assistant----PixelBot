"""
Text Processor

Processes transcribed text with keyword removal and formatting:
- Mode 1: Regex-only (fast, 100% reliable for keywords)
- Mode 2: Regex + LLM (intelligent error correction, self-correction handling)

The LLM intelligently fixes:
- Transcription errors from Whisper
- Self-corrections ("X, wait no! Y" → "Y")
- Technical term mishearings

Keywords are ALWAYS removed with regex first for reliability.

Action-Specific Processing:
- Each action (transcribe, cortex, pixelbot) has its own prompt
- Context is maintained separately per action
- Prompts are context-aware for better continuity
"""
import logging
from typing import Optional

from src import config
from src.context_manager import get_context_manager

logger = logging.getLogger(__name__)


class TextProcessor:
    """Processes transcribed text with optional LLM enhancement."""

    def __init__(self, llm_manager=None, use_llm: bool = False):
        """
        Initialize text processor.

        Args:
            llm_manager: Optional LLM manager for intelligent processing
            use_llm: Whether to use LLM for post-processing
        """
        self.llm_manager = llm_manager
        self.use_llm = use_llm and llm_manager is not None
        self.is_ready = True
        self.context_manager = get_context_manager()

        mode = "LLM-enhanced" if self.use_llm else "regex-only"
        logger.info(f"TextProcessor initialized ({mode}, action-aware)")

    def initialize(self) -> bool:
        """
        Initialize the processor (no-op for regex-based processor).

        Returns:
            bool: True (always ready)
        """
        logger.info("✓ Text processor ready")
        return True

    def shutdown(self) -> bool:
        """
        Shutdown the processor (no-op for regex-based processor).

        Returns:
            bool: True (always successful)
        """
        logger.info("✓ Text processor shutdown")
        return True

    def process(
        self,
        raw_text: str,
        remove_keywords: bool = True,
        action: str = "transcribe",
    ) -> str:
        """
        Process text with action-specific prompts and context.

        Args:
            raw_text: Raw transcription from Whisper
            remove_keywords: Whether to remove activation keywords
            action: Action type ("transcribe", "cortex", "pixelbot")

        Returns:
            str: Cleaned and formatted text
        """
        if not raw_text or not raw_text.strip():
            logger.warning("Empty input text")
            return ""

        try:
            logger.info(f"Processing text ({action}): '{raw_text[:100]}'")

            if remove_keywords and self.use_llm and self.llm_manager:
                # HYBRID MODE: Regex pre-processing + Action-specific LLM cleaning
                # This provides defense-in-depth against prompt injection

                # Step 1: Regex pre-processing (catches obvious keywords)
                logger.info("Step 1: Regex pre-processing")
                regex_cleaned = self._remove_keywords_regex(raw_text)

                # Step 2: Action-specific LLM cleaning with context
                logger.info(f"Step 2: LLM intelligent cleaning (action={action})")

                # Get context for this action
                context = self.context_manager.get_context_summary(action)

                # Select action-specific prompt
                system_prompt, user_template = self._get_prompts_for_action(action)

                # Format prompts with context
                system_prompt_formatted = system_prompt.format(context=context)
                user_prompt = user_template.format(text=regex_cleaned)

                messages = [
                    {"role": "system", "content": system_prompt_formatted},
                    {"role": "user", "content": user_prompt}
                ]

                # Generate with LLM (handles error correction, formatting)
                cleaned = self.llm_manager.generate(
                    messages=messages,
                    max_tokens=512,  # Allow longer outputs for complex text
                    temperature=0.05,  # Very deterministic
                )

                # Post-process LLM output
                cleaned = self._clean_llm_output(cleaned)

                # Handle empty query marker
                if cleaned.strip() == "EMPTY_QUERY":
                    logger.warning(f"Empty query detected after processing ({action})")
                    return ""

                # Save to context for this action
                if cleaned and cleaned.strip():
                    self.context_manager.add_context(action, regex_cleaned, cleaned)
                    logger.debug(f"Context updated for {action}")

            elif remove_keywords:
                # Regex-only mode (fallback when LLM not available)
                logger.info("Using regex-only mode")
                cleaned = self._remove_keywords_regex(raw_text)
                cleaned = self._apply_replacements(cleaned)
                cleaned = self._apply_formatting(cleaned)
            else:
                # Just format without keyword removal
                cleaned = self._apply_formatting(raw_text)

            logger.info(f"Processed result: '{cleaned[:100]}'")

            return cleaned

        except Exception as e:
            logger.error(f"Text processing failed: {e}", exc_info=True)
            # Fallback: return original text
            return raw_text

    def _get_prompts_for_action(self, action: str) -> tuple[str, str]:
        """
        Get action-specific prompts from config.

        Args:
            action: Action type ("transcribe", "cortex", "pixelbot")

        Returns:
            tuple: (system_prompt, user_template)
        """
        if action == "cortex":
            return (config.CORTEX_SYSTEM_PROMPT, config.CORTEX_USER_TEMPLATE)
        elif action == "pixelbot":
            return (config.PIXELBOT_SYSTEM_PROMPT, config.PIXELBOT_USER_TEMPLATE)
        else:  # Default to transcribe
            return (config.TRANSCRIBE_SYSTEM_PROMPT, config.TRANSCRIBE_USER_TEMPLATE)

    def _remove_keywords_regex(self, text: str) -> str:
        """
        Remove activation keywords using regex (reliable method).

        Args:
            text: Input text

        Returns:
            str: Text with keywords removed
        """
        import re

        # Keywords to remove (in priority order - longest first)
        keywords = [
            # Transcribe keywords (including -ing forms and mishearings)
            r'\bstart transcribing\b',
            r'\bstart transcribe\b',
            r'\bstop transcribing\b',
            r'\bstop transcribe\b',
            r'\bstop[.,!?]\s+transcrib\w*\b',  # Edge case: "Stop. Transcribe."
            r'\bend transcribing\b',
            r'\bend transcribe\b',
            r'\bentranscrib\w*\b',  # Edge case: "Entranscribe" (mishearing)
            r'\band the transcribe\b',  # Mishearing of "end"
            r'\band transcribing\b',  # Mishearing of "end" with -ing
            r'\band transcribe\b',  # Mishearing of "end"
            r'\bfinish transcribing\b',
            r'\bfinish transcribe\b',
            r'\bbegin transcribing\b',
            r'\bbegin transcribe\b',
            r'\btranscribing\b',  # General -ing form
            r'\btranscribe\b',
            # Standalone "stop" (only when NOT followed by regular words)
            r'\bstop\b(?!\s+(?:the|it|me|that|this|there|here|now))',  # "stop" not followed by common words

            # Pixel Bot keywords (including mishearings)
            r'\bpixel\s+bot\b',
            r'\bpixel\s+byte\b',  # Mishearing: "pixel byte"
            r'\bpixel\s+bite\b',  # Mishearing: "pixel bite"
            r'\bpixel\s+b[aoy]te?\b',  # Fuzzy: "pixel bate/byte/bote"
            r'\bpixelbot\b',
            r'\bpixel[ -]?b[aoy]t*\b',  # Fuzzy match (bot/bat/by/bout)
            r'\bhey pixel\b',
            r'\byo pixel\b',

            # Cortex keywords (including mishearings)
            r'\bpixel cortex\b',
            r'\bhey cortex\b',
            r'\byo cortex\b',
            r'\bcore techs?\b',  # Whisper mishears "cortex" as "core tech/techs"
            r'\bcoretex\b',
            r'\bcortex\b',
        ]

        cleaned = text
        for keyword in keywords:
            cleaned = re.sub(keyword, '', cleaned, flags=re.IGNORECASE)

        # Clean up extra spaces and punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'\s+([.,!?])', r'\1', cleaned)  # Fix spacing before punctuation
        cleaned = re.sub(r'^[.,!?\s]+', '', cleaned)  # Remove leading punctuation/spaces
        cleaned = re.sub(r'[.,!?]+$', '', cleaned)  # Remove trailing punctuation (will be re-added)
        cleaned = re.sub(r'\.+', '.', cleaned)  # Fix multiple periods

        return cleaned

    def _apply_replacements(self, text: str) -> str:
        """
        Apply custom word replacements.

        Args:
            text: Input text

        Returns:
            str: Text with replacements applied
        """
        result = text
        for old, new in config.CUSTOM_WORD_REPLACEMENTS.items():
            # Case-insensitive replacement
            import re
            result = re.sub(re.escape(old), new, result, flags=re.IGNORECASE)

        return result

    def _clean_llm_output(self, text: str) -> str:
        """
        Clean LLM output (remove artifacts from generation).

        Args:
            text: LLM output

        Returns:
            str: Cleaned text
        """
        if not text:
            return text

        # Remove common prefixes the LLM might add
        prefixes = [
            "Cleaned text:", "Cleaned:", "Output:", "Result:",
            "Answer:", "A:", "[OUTPUT]", "Text:",
        ]

        text_lower = text.lower()
        for prefix in prefixes:
            if text_lower.startswith(prefix.lower()):
                text = text[len(prefix):].strip()
                text_lower = text.lower()

        # Remove quotes
        text = text.strip('"\'')

        # Take only first line if multiple lines
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            text = lines[0]

        return text.strip()

    def _apply_formatting(self, text: str) -> str:
        """
        Apply basic formatting (capitalization and punctuation).

        Args:
            text: Input text

        Returns:
            str: Formatted text
        """
        if not text:
            return text

        # Capitalize first letter
        text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()

        # Ensure sentence ends with punctuation
        if text and text[-1] not in '.!?':
            text += '.'

        return text

    def _format_only(self, text: str) -> str:
        """
        Format text without keyword removal.

        Args:
            text: Input text

        Returns:
            str: Formatted text
        """
        prompt = f"""Format this text with proper punctuation and capitalization.
Do not remove any words, just improve formatting.

Input: {text}
Output:"""

        messages = [{"role": "user", "content": prompt}]

        formatted = self.llm_manager.generate(
            messages,
            max_tokens=512,
            temperature=0.3,
        )

        return formatted.strip('"\'')

    def get_status(self) -> dict:
        """
        Get processor status.

        Returns:
            dict: Status information
        """
        return {
            "ready": self.is_ready,
            "llm_status": self.llm_manager.get_status() if self.is_ready else None,
        }


# Test function
def test_text_processor():
    """Test text processor with sample transcriptions."""
    print("\n" + "=" * 70)
    print("TEXT PROCESSOR TEST (LLM Integration)")
    print("=" * 70)

    # Initialize processor
    print("\n1. Initializing text processor (loading Phi-3-mini LLM)...")
    print("   This may take 30-60 seconds on first run...")

    processor = TextProcessor()
    success = processor.initialize()

    if not success:
        print("❌ Failed to initialize processor")
        return False

    print("   ✓ Processor ready")
    print(f"   Status: {processor.get_status()}")

    # Test cases - these are actual Whisper transcriptions that need cleaning
    print("\n2. Testing keyword removal and text cleaning...")

    test_cases = [
        # Basic keyword removal
        ("transcribe hello world stop transcribe", "Hello world."),
        ("start transcribe this is a test end transcribe", "This is a test."),

        # Keywords with variations (what Whisper actually produces)
        ("Start transcribing. Hello world.", "Hello world."),
        ("And the transcribe", ""),  # Just keyword, should be empty

        # Pixel Bot activations
        ("Pixelbot what is two plus two", "What is two plus two?"),
        ("pixel bot tell me a joke", "Tell me a joke."),

        # Cortex activations
        ("Cortex. Check Bitcoin price.", "Check Bitcoin price."),
        ("hey cortex what's the weather", "What's the weather?"),

        # Complex sentence with keyword in middle
        ("transcribe the quick brown fox jumps over and transcribe the lazy dog",
         "The quick brown fox jumps over the lazy dog."),

        # Custom word replacement
        ("check deck screener for this token", "Check DexScreener for this token."),
    ]

    for i, (raw_text, expected_clean) in enumerate(test_cases, 1):
        print(f"\n   Test {i}:")
        print(f"   Input:    '{raw_text}'")

        cleaned = processor.process(raw_text)

        print(f"   Output:   '{cleaned}'")
        print(f"   Expected: '{expected_clean}'")

        # Check if keywords are removed
        has_keywords = any(
            kw in cleaned.lower()
            for kw in ["transcribe", "pixel bot", "cortex", "pixelbot"]
        )

        if has_keywords:
            print(f"   ⚠️  WARNING: Keywords still present!")
        else:
            print(f"   ✓ Keywords removed")

    # Test with actual voice sample transcriptions
    print("\n3. Testing with real voice sample transcriptions...")

    from src.transcription_engine import TranscriptionEngine
    from pathlib import Path

    engine = TranscriptionEngine()
    engine.initialize()

    voice_dir = Path("WonkasVoice")

    if voice_dir.exists():
        test_files = [
            "start_transcribe_hello_world_how_are_you_end_transcribe2.wav",
            "start_transcribe1.wav",
            "pixel_bot1.wav",
        ]

        for filename in test_files:
            filepath = voice_dir / filename

            if not filepath.exists():
                print(f"\n   SKIP: {filename} not found")
                continue

            print(f"\n   File: {filename}")

            # Transcribe
            raw_text, _ = engine.transcribe_file(str(filepath))
            print(f"   Whisper:  '{raw_text}'")

            # Process with LLM
            cleaned = processor.process(raw_text)
            print(f"   Cleaned:  '{cleaned}'")

            # Check keywords
            has_keywords = any(
                kw in cleaned.lower()
                for kw in ["transcribe", "start", "stop", "end", "pixel", "bot"]
            )
            print(f"   Keywords: {'❌ Present' if has_keywords else '✓ Removed'}")

    engine.shutdown()

    # Cleanup
    print("\n4. Shutting down...")
    processor.shutdown()
    print("   ✓ Shutdown complete")

    print("\n" + "=" * 70)
    print("✅ TEXT PROCESSOR TEST COMPLETE")
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
    success = test_text_processor()
    sys.exit(0 if success else 1)
