"""
Whisper Model Manager

Handles loading, unloading, and management of the Whisper speech recognition model.
Uses faster-whisper for GPU-accelerated inference.

Target VRAM: 2GB (FP16)
"""
import logging
import time
from pathlib import Path
from typing import Optional

import torch
from faster_whisper import WhisperModel

from src import config

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages the Whisper speech recognition model."""

    def __init__(self):
        """Initialize the model manager."""
        self.model: Optional[WhisperModel] = None
        self.is_loaded = False
        self.load_time: Optional[float] = None
        self.vram_usage: Optional[float] = None

    def load(self) -> bool:
        """
        Load the Whisper model into GPU memory.

        Returns:
            bool: True if successful, False otherwise
        """
        if self.is_loaded:
            logger.info("Whisper model already loaded")
            return True

        try:
            logger.info(f"Loading Whisper model: {config.WHISPER_MODEL_SIZE}")
            start_time = time.time()

            # Get initial VRAM
            initial_vram = self._get_vram_used()

            # Load model with faster-whisper
            self.model = WhisperModel(
                model_size_or_path=config.WHISPER_MODEL_SIZE,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
                download_root=config.WHISPER_DOWNLOAD_ROOT,
                local_files_only=False,  # Allow download on first run
            )

            # Calculate load time and VRAM usage
            self.load_time = time.time() - start_time
            self.vram_usage = self._get_vram_used() - initial_vram
            self.is_loaded = True

            logger.info(
                f"✓ Whisper model loaded successfully in {self.load_time:.2f}s"
            )
            logger.info(f"  VRAM usage: {self.vram_usage:.2f}GB")
            logger.info(f"  Total VRAM: {self._get_vram_used():.2f}GB")

            return True

        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}", exc_info=True)
            self.is_loaded = False
            return False

    def unload(self) -> bool:
        """
        Unload the Whisper model from GPU memory.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_loaded:
            logger.info("Whisper model not loaded")
            return True

        try:
            logger.info("Unloading Whisper model...")

            # Delete model
            self.model = None
            self.is_loaded = False

            # Force garbage collection and clear CUDA cache
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

            logger.info("✓ Whisper model unloaded")
            logger.info(f"  VRAM after unload: {self._get_vram_used():.2f}GB")

            return True

        except Exception as e:
            logger.error(f"Failed to unload Whisper model: {e}", exc_info=True)
            return False

    def transcribe(
        self,
        audio: any,
        language: str = "en",
        task: str = "transcribe",
    ) -> tuple[str, dict]:
        """
        Transcribe audio using Whisper.

        Args:
            audio: Audio data (numpy array, 16kHz sample rate)
            language: Language code (default: "en")
            task: "transcribe" or "translate"

        Returns:
            tuple: (transcription_text, info_dict)
        """
        if not self.is_loaded:
            raise RuntimeError("Whisper model not loaded. Call load() first.")

        try:
            # Transcribe with faster-whisper
            segments, info = self.model.transcribe(
                audio,
                language=language,
                task=task,
                beam_size=config.WHISPER_BEAM_SIZE,
                vad_filter=False,  # We do our own VAD
                word_timestamps=False,
            )

            # Collect all segments into full text
            full_text = " ".join([segment.text for segment in segments])

            # Create info dict
            info_dict = {
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
            }

            logger.debug(f"Transcription: '{full_text}'")
            logger.debug(f"Info: {info_dict}")

            return full_text.strip(), info_dict

        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return "", {}

    def get_status(self) -> dict:
        """
        Get model status information.

        Returns:
            dict: Status information
        """
        return {
            "loaded": self.is_loaded,
            "model_size": config.WHISPER_MODEL_SIZE,
            "device": config.WHISPER_DEVICE,
            "compute_type": config.WHISPER_COMPUTE_TYPE,
            "load_time": self.load_time,
            "vram_usage": self.vram_usage,
            "current_vram": self._get_vram_used() if torch.cuda.is_available() else None,
        }

    def _get_vram_used(self) -> float:
        """
        Get current VRAM usage in GB.

        Returns:
            float: VRAM usage in GB
        """
        if not torch.cuda.is_available():
            return 0.0

        return torch.cuda.memory_allocated(0) / 1e9

    def __del__(self):
        """Cleanup on deletion."""
        if self.is_loaded:
            self.unload()


# Convenience function for standalone testing
def test_model_manager():
    """Test the model manager."""
    import numpy as np

    print("=== Testing Whisper Model Manager ===\n")

    # Initialize
    manager = ModelManager()
    print(f"Initial status: {manager.get_status()}\n")

    # Load model
    print("Loading model...")
    success = manager.load()
    print(f"Load success: {success}\n")

    if success:
        print(f"Status after load: {manager.get_status()}\n")

        # Test transcription with dummy audio (5 seconds of silence)
        print("Testing transcription with dummy audio...")
        dummy_audio = np.zeros(16000 * 5, dtype=np.float32)

        text, info = manager.transcribe(dummy_audio)
        print(f"Transcription: '{text}'")
        print(f"Info: {info}\n")

        # Unload
        print("Unloading model...")
        manager.unload()
        print(f"Status after unload: {manager.get_status()}\n")

    print("=== Test Complete ===")


if __name__ == "__main__":
    # Set up basic logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run test
    test_model_manager()
