"""
Keyword Detector

Detects activation keywords in transcribed text using regex patterns.
Continuously monitors audio buffer and triggers mode changes.
"""
import logging
import re
import threading
import time
from typing import Optional, Callable, Dict

import numpy as np

from src import config
from src.transcription_engine import TranscriptionEngine

logger = logging.getLogger(__name__)


class KeywordDetector:
    """Detects activation keywords in audio stream."""

    def __init__(
        self,
        transcription_engine: TranscriptionEngine,
        callback: Optional[Callable[[str, str], None]] = None
    ):
        """
        Initialize keyword detector.

        Args:
            transcription_engine: Transcription engine instance
            callback: Callback function(keyword_type, full_text) called when keyword detected
        """
        self.transcription_engine = transcription_engine
        self.callback = callback

        self.is_running = False
        self.detection_thread: Optional[threading.Thread] = None

        # Compile regex patterns for efficiency
        self.patterns: Dict[str, list] = {}
        for keyword_type, pattern_list in config.KEYWORDS.items():
            self.patterns[keyword_type] = [
                re.compile(pattern, re.IGNORECASE) for pattern in pattern_list
            ]

        logger.info("KeywordDetector initialized")

    def start(self, audio_buffer_callback: Callable[[], np.ndarray]) -> bool:
        """
        Start keyword detection.

        Args:
            audio_buffer_callback: Function that returns current audio buffer

        Returns:
            bool: True if successful
        """
        if self.is_running:
            logger.warning("KeywordDetector already running")
            return True

        if not self.transcription_engine.is_ready:
            logger.error("TranscriptionEngine not ready")
            return False

        self.audio_buffer_callback = audio_buffer_callback
        self.is_running = True

        # Start detection thread
        self.detection_thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
        )
        self.detection_thread.start()

        logger.info("KeywordDetector started")
        return True

    def stop(self) -> bool:
        """Stop keyword detection."""
        if not self.is_running:
            return True

        logger.info("Stopping KeywordDetector...")
        self.is_running = False

        if self.detection_thread:
            self.detection_thread.join(timeout=5.0)

        logger.info("KeywordDetector stopped")
        return True

    def _detection_loop(self):
        """Main detection loop (runs in separate thread)."""
        logger.info("Detection loop started")

        while self.is_running:
            try:
                # Get current audio buffer
                audio_buffer = self.audio_buffer_callback()

                if len(audio_buffer) < config.SAMPLE_RATE * 0.5:
                    # Not enough audio yet (less than 0.5 seconds)
                    time.sleep(config.KEYWORD_CHECK_INTERVAL)
                    continue

                # For keyword detection, only transcribe the LAST 8 seconds
                # This makes detection more reliable and faster
                detection_window_seconds = 8
                detection_window_samples = int(detection_window_seconds * config.SAMPLE_RATE)

                if len(audio_buffer) > detection_window_samples:
                    # Use only the last 8 seconds
                    audio_to_transcribe = audio_buffer[-detection_window_samples:]
                else:
                    # Use full buffer if less than 8 seconds
                    audio_to_transcribe = audio_buffer

                # Transcribe detection window
                text, _ = self.transcription_engine.transcribe(audio_to_transcribe)

                if not text:
                    time.sleep(config.KEYWORD_CHECK_INTERVAL)
                    continue

                logger.debug(f"Buffer transcription: '{text}'")

                # Check for keywords
                detected = self._check_keywords(text)

                if detected:
                    keyword_type, matched_text = detected
                    logger.info(f"✓ Keyword detected: {keyword_type} ('{matched_text}')")

                    # Call callback if provided
                    if self.callback:
                        self.callback(keyword_type, text)

                # Wait before next check
                time.sleep(config.KEYWORD_CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"Error in detection loop: {e}", exc_info=True)
                time.sleep(config.KEYWORD_CHECK_INTERVAL)

        logger.info("Detection loop ended")

    def _check_keywords(self, text: str) -> Optional[tuple]:
        """
        Check if text contains any activation keywords.

        Args:
            text: Transcribed text

        Returns:
            tuple: (keyword_type, matched_text) or None
        """
        # Check each keyword type in priority order
        # Priority: end keywords first (so we can stop active modes)
        priority_order = [
            "transcribe_end",
            "transcribe_start",
            "pixel_bot",
            "cortex",
        ]

        for keyword_type in priority_order:
            if keyword_type not in self.patterns:
                continue

            for pattern in self.patterns[keyword_type]:
                match = pattern.search(text)
                if match:
                    return (keyword_type, match.group(0))

        return None

    def detect_in_text(self, text: str) -> Optional[tuple]:
        """
        Manually check if text contains keywords (synchronous).

        Args:
            text: Text to check

        Returns:
            tuple: (keyword_type, matched_text) or None
        """
        return self._check_keywords(text)

    def get_status(self) -> dict:
        """
        Get detector status.

        Returns:
            dict: Status information
        """
        return {
            "running": self.is_running,
            "patterns_loaded": len(self.patterns),
            "check_interval": config.KEYWORD_CHECK_INTERVAL,
        }


# Test function
def test_keyword_detector():
    """Test keyword detector with sample transcriptions."""
    print("\n" + "=" * 70)
    print("KEYWORD DETECTOR TEST")
    print("=" * 70)

    # Initialize transcription engine
    print("\n1. Initializing transcription engine...")
    engine = TranscriptionEngine()
    if not engine.initialize():
        print("❌ Failed to initialize engine")
        return False

    print("   ✓ Engine ready")

    # Test keyword detection
    print("\n2. Testing keyword detection patterns...")

    test_cases = [
        ("start transcribe hello world", "transcribe_start"),
        ("hello world stop transcribe", "transcribe_end"),
        ("transcribe this is a test", "transcribe_start"),
        ("pixel bot what is the time", "pixel_bot"),
        ("hey pixel tell me a joke", "pixel_bot"),
        ("cortex check bitcoin price", "cortex"),
        ("this has no keywords", None),
    ]

    detector = KeywordDetector(engine)

    for text, expected_type in test_cases:
        result = detector.detect_in_text(text)

        if result:
            keyword_type, matched = result
            status = "✓" if keyword_type == expected_type else "❌"
            print(f"   {status} '{text}' -> {keyword_type} ('{matched}')")
        else:
            status = "✓" if expected_type is None else "❌"
            print(f"   {status} '{text}' -> No keywords detected")

    # Test with actual voice samples
    print("\n3. Testing with voice sample transcriptions...")

    from pathlib import Path
    voice_dir = Path("WonkasVoice")

    if voice_dir.exists():
        test_files = [
            ("start_transcribe1.wav", "transcribe_start"),
            ("end_transcribe1.wav", "transcribe_end"),
            ("pixel_bot1.wav", "pixel_bot"),
            ("cortex1.wav", "cortex"),
        ]

        for filename, expected_type in test_files:
            filepath = voice_dir / filename

            if not filepath.exists():
                print(f"   SKIP: {filename} not found")
                continue

            # Transcribe
            text, _ = engine.transcribe_file(str(filepath))

            # Detect keywords
            result = detector.detect_in_text(text)

            if result:
                keyword_type, matched = result
                status = "✓" if keyword_type == expected_type else "⚠️"
                print(f"   {status} {filename}: '{text}' -> {keyword_type}")
            else:
                print(f"   ❌ {filename}: '{text}' -> No keywords (expected {expected_type})")

    # Cleanup
    print("\n4. Shutting down...")
    engine.shutdown()
    print("   ✓ Shutdown complete")

    print("\n" + "=" * 70)
    print("✅ KEYWORD DETECTOR TEST COMPLETE")
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
    success = test_keyword_detector()
    sys.exit(0 if success else 1)
