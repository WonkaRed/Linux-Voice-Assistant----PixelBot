"""
Transcription Engine

High-level wrapper for Whisper model transcription.
Handles audio preprocessing and transcription workflow.
"""
import logging
import time
from typing import Tuple, Optional

import numpy as np
import librosa

from src import config
from src.model_manager import ModelManager

logger = logging.getLogger(__name__)


class TranscriptionEngine:
    """High-level transcription engine using Whisper."""

    def __init__(self):
        """Initialize transcription engine."""
        self.model_manager = ModelManager()
        self.is_ready = False

    def initialize(self) -> bool:
        """
        Initialize the engine (load Whisper model).

        Returns:
            bool: True if successful
        """
        if self.is_ready:
            logger.info("Transcription engine already initialized")
            return True

        logger.info("Initializing transcription engine...")
        success = self.model_manager.load()

        if success:
            self.is_ready = True
            logger.info("✓ Transcription engine ready")
        else:
            logger.error("Failed to initialize transcription engine")

        return success

    def shutdown(self) -> bool:
        """
        Shutdown the engine (unload model).

        Returns:
            bool: True if successful
        """
        if not self.is_ready:
            return True

        logger.info("Shutting down transcription engine...")
        success = self.model_manager.unload()

        if success:
            self.is_ready = False
            logger.info("✓ Transcription engine shutdown")

        return success

    def transcribe(
        self,
        audio: np.ndarray,
        language: str = "en",
    ) -> Tuple[str, dict]:
        """
        Transcribe audio to text.

        Args:
            audio: Audio data (numpy array, any sample rate)
            language: Language code (default: "en")

        Returns:
            tuple: (transcription_text, info_dict)
        """
        if not self.is_ready:
            raise RuntimeError("Transcription engine not initialized. Call initialize() first.")

        try:
            # Ensure audio is 16kHz (Whisper requirement)
            audio_16k = self._ensure_16khz(audio)

            # Get duration
            duration = len(audio_16k) / config.SAMPLE_RATE

            logger.info(f"Transcribing {duration:.2f}s of audio...")
            start_time = time.time()

            # Transcribe with Whisper
            text, info = self.model_manager.transcribe(audio_16k, language=language)

            # Calculate metrics
            elapsed = time.time() - start_time
            rtf = elapsed / duration if duration > 0 else 0  # Real-time factor

            logger.info(f"Transcription complete in {elapsed:.2f}s (RTF: {rtf:.2f}x)")
            logger.info(f"Result: '{text[:100]}{'...' if len(text) > 100 else ''}'")

            # Add timing info
            info['processing_time'] = elapsed
            info['real_time_factor'] = rtf

            return text, info

        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return "", {}

    def transcribe_file(
        self,
        file_path: str,
        language: str = "en",
    ) -> Tuple[str, dict]:
        """
        Transcribe an audio file.

        Args:
            file_path: Path to audio file
            language: Language code (default: "en")

        Returns:
            tuple: (transcription_text, info_dict)
        """
        if not self.is_ready:
            raise RuntimeError("Transcription engine not initialized. Call initialize() first.")

        try:
            logger.info(f"Loading audio file: {file_path}")

            # Load audio file (librosa handles various formats)
            audio, sr = librosa.load(file_path, sr=config.SAMPLE_RATE, mono=True)

            logger.info(f"Loaded {len(audio)/sr:.2f}s audio at {sr}Hz")

            # Transcribe
            return self.transcribe(audio, language=language)

        except Exception as e:
            logger.error(f"Failed to transcribe file: {e}", exc_info=True)
            return "", {}

    def _ensure_16khz(self, audio: np.ndarray, current_sr: Optional[int] = None) -> np.ndarray:
        """
        Ensure audio is at 16kHz sample rate.

        Args:
            audio: Audio data
            current_sr: Current sample rate (if known, otherwise assumes 16kHz)

        Returns:
            np.ndarray: Audio at 16kHz
        """
        # If no current sample rate specified, assume it's already 16kHz
        if current_sr is None or current_sr == config.SAMPLE_RATE:
            return audio

        # Resample if needed
        logger.debug(f"Resampling from {current_sr}Hz to {config.SAMPLE_RATE}Hz")
        audio_16k = librosa.resample(audio, orig_sr=current_sr, target_sr=config.SAMPLE_RATE)

        return audio_16k

    def get_status(self) -> dict:
        """
        Get engine status.

        Returns:
            dict: Status information
        """
        return {
            "ready": self.is_ready,
            "model_status": self.model_manager.get_status() if self.is_ready else None,
        }

    def __del__(self):
        """Cleanup on deletion."""
        if self.is_ready:
            self.shutdown()


# Test function
def test_transcription_engine():
    """Test transcription engine with voice samples."""
    import os
    from pathlib import Path

    print("\n" + "=" * 70)
    print("TRANSCRIPTION ENGINE TEST")
    print("=" * 70)

    # Initialize engine
    engine = TranscriptionEngine()

    print("\n1. Initializing engine...")
    success = engine.initialize()

    if not success:
        print("❌ Failed to initialize engine")
        return False

    print(f"   ✓ Engine ready")
    print(f"   Status: {engine.get_status()}")

    # Test with voice samples
    voice_dir = Path("WonkasVoice")

    if not voice_dir.exists():
        print("\n⚠️  WonkasVoice directory not found, using dummy audio")

        # Test with dummy audio
        print("\n2. Testing with dummy audio (3 seconds of silence)...")
        dummy_audio = np.zeros(16000 * 3, dtype=np.float32)
        text, info = engine.transcribe(dummy_audio)

        print(f"   Transcription: '{text}'")
        print(f"   Processing time: {info.get('processing_time', 0):.2f}s")

    else:
        # Test with real voice samples
        test_files = [
            "start_transcribe1.wav",
            "end_transcribe1.wav",
            "pixel_bot1.wav",
            "start_transcribe_hello_world_how_are_you_end_transcribe2.wav",
        ]

        print(f"\n2. Testing with voice samples from {voice_dir}/")

        for i, filename in enumerate(test_files, 1):
            filepath = voice_dir / filename

            if not filepath.exists():
                print(f"\n   Test {i}: {filename} - SKIP (not found)")
                continue

            print(f"\n   Test {i}: {filename}")
            text, info = engine.transcribe_file(str(filepath))

            print(f"   Transcription: '{text}'")
            print(f"   Duration: {info.get('duration', 0):.2f}s")
            print(f"   Processing: {info.get('processing_time', 0):.2f}s")
            print(f"   RTF: {info.get('real_time_factor', 0):.2f}x")

    # Shutdown
    print("\n3. Shutting down engine...")
    engine.shutdown()
    print("   ✓ Engine shutdown")

    print("\n" + "=" * 70)
    print("✅ TRANSCRIPTION ENGINE TEST COMPLETE")
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
    success = test_transcription_engine()
    sys.exit(0 if success else 1)
