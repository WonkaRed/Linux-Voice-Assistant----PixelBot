"""
Speech-to-Text Engine - Faster-Whisper for accurate speech recognition.

Features:
- GPU-accelerated transcription via faster-whisper
- VAD (Voice Activity Detection) filtering
- Real-time transcription support
- Multiple model sizes for speed/accuracy tradeoff
"""
import logging
import threading
import time
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class STTEngine:
    """Speech-to-text engine using Faster-Whisper."""

    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 0,
        device_index: int = 0,
    ):
        """
        Initialize STT engine.

        Args:
            model_size: Whisper model (e.g. large-v3-turbo, large-v3, medium.en)
            device: Device to use (cuda, cpu)
            compute_type: Compute type (float16 for cuda; int8 for cpu)
            cpu_threads: CPU threads (0 = use all cores). Matters a lot for
                         CPU latency — the default 0 lets us pass all 16.
            device_index: Which GPU to use when device="cuda" (for multi-GPU
                          machines). Ignored on CPU.
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.device_index = device_index
        # 0 → let CTranslate2 use every core (CPU transcription is ~2× faster
        # with all 16 threads vs the library's conservative default).
        import os as _os
        self.cpu_threads = cpu_threads or (_os.cpu_count() or 4)
        self.model = None
        self.sample_rate = 16000  # Whisper requires 16kHz
        self._switch_lock = threading.Lock()

        self._load_model()

    def _load_model(self):
        """Load the Whisper model with automatic CPU fallback."""
        try:
            from faster_whisper import WhisperModel

            logger.info(f"Loading Whisper model: {self.model_size} ({self.device}, {self.compute_type})")
            start = time.time()

            # Try requested device first
            try:
                self.model = WhisperModel(
                    model_size_or_path=self.model_size,
                    device=self.device,
                    device_index=self.device_index,
                    compute_type=self.compute_type,
                    cpu_threads=self.cpu_threads,
                )

                # Verify CUDA transcription works (catches cuDNN issues early)
                if self.device == "cuda":
                    test_audio = np.zeros(1600, dtype=np.float32)  # 0.1s silence
                    list(self.model.transcribe(test_audio, language="en"))
                    logger.info("CUDA transcription verified")

            except Exception as cuda_error:
                if self.device == "cuda":
                    logger.warning(f"CUDA failed ({cuda_error}), falling back to CPU")
                    self.device = "cpu"
                    self.compute_type = "int8"  # Faster on CPU
                    self.model = WhisperModel(
                        model_size_or_path=self.model_size,
                        device="cpu",
                        compute_type="int8",
                        cpu_threads=self.cpu_threads,
                    )
                else:
                    raise

            elapsed = time.time() - start
            logger.info(f"Whisper model loaded in {elapsed:.2f}s (device: {self.device})")

        except ImportError:
            logger.error("faster-whisper not installed. Install with: pip install faster-whisper")
            raise
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def transcribe(
        self,
        audio: np.ndarray,
        language: str = "en",
    ) -> Tuple[str, dict]:
        """
        Transcribe audio to text.

        Args:
            audio: Audio data (numpy array, 16kHz mono float32)
            language: Language code

        Returns:
            Tuple of (text, info_dict)
        """
        if not self.model:
            logger.error("STT model not loaded")
            return "", {}

        try:
            # Ensure audio is the right format
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            # Normalize if needed
            if np.abs(audio).max() > 1.0:
                audio = audio / 32768.0

            duration = len(audio) / self.sample_rate
            logger.info(f"Transcribing {duration:.2f}s of audio...")

            start = time.time()

            # Transcribe with settings optimized for short voice commands
            segments, info = self.model.transcribe(
                audio,
                language=language,
                beam_size=5,
                vad_filter=False,  # Disabled - doesn't work well with TTS audio
                condition_on_previous_text=False,  # Prevents "You" hallucinations
                initial_prompt="Voice command transcription.",  # Helps model understand context
            )

            # Collect text
            text = " ".join([segment.text for segment in segments]).strip()

            # Filter out hallucinations (model sometimes returns the prompt when there's no speech)
            hallucinations = [
                "voice command transcription",
                "voice command transcription.",
                "thank you",
                "thanks for watching",
                "you",
            ]
            if text.lower().strip().rstrip('.') in [h.rstrip('.') for h in hallucinations]:
                logger.warning(f"Filtered hallucination: '{text}'")
                text = ""

            elapsed = time.time() - start
            rtf = elapsed / duration if duration > 0 else 0

            logger.info(f"Transcription complete in {elapsed:.2f}s (RTF: {rtf:.2f}x)")
            logger.debug(f"Result: '{text}'")

            return text, {
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "processing_time": elapsed,
                "rtf": rtf,
            }

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return "", {}

    def transcribe_file(self, file_path: str, language: str = "en") -> Tuple[str, dict]:
        """
        Transcribe an audio file.

        Args:
            file_path: Path to audio file
            language: Language code

        Returns:
            Tuple of (text, info_dict)
        """
        try:
            import librosa

            logger.info(f"Loading audio: {file_path}")
            audio, sr = librosa.load(file_path, sr=self.sample_rate, mono=True)

            return self.transcribe(audio, language=language)

        except Exception as e:
            logger.error(f"Failed to load audio file: {e}")
            return "", {}

    def load(self) -> bool:
        """Load model to GPU. Returns True if successful."""
        if self.model is not None:
            return True
        try:
            self._load_model()
            return self.model is not None
        except Exception as e:
            logger.error(f"Model load failed: {e}")
            return False

    def unload(self):
        """Unload model from GPU, free VRAM."""
        if self.model is None:
            return
        logger.info("Unloading STT model...")
        del self.model
        self.model = None
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        logger.info("STT model unloaded")

    def switch_device(self, device: str, device_index: int = 0, compute_type: Optional[str] = None) -> bool:
        """
        Move the model to a different device in place, keeping this same
        STTEngine object alive (so callers holding a reference — e.g. the
        streaming transcriber — automatically pick up the new device on
        their next call; nothing else needs to be rewired).

        Thread-safe: callers should still hold whatever lock guards
        transcribe() (e.g. the streaming poll lock) while calling this, so a
        switch never races an in-flight transcription. This method also
        holds its own lock as a second guard against concurrent switches.

        On any failure, falls back to CPU (never leaves the engine with no
        usable model) and returns False.
        """
        with self._switch_lock:
            if device == self.device and (device != "cuda" or device_index == self.device_index):
                return True  # already there — no-op

            prior_device, prior_index, prior_compute = self.device, self.device_index, self.compute_type
            target_compute = compute_type or ("float16" if device == "cuda" else "int8")

            self.unload()
            self.device = device
            self.device_index = device_index
            self.compute_type = target_compute
            try:
                self._load_model()
                if self.model is not None and self.device == device:
                    logger.info(f"STT switched to {self.device}" + (f" (GPU {device_index})" if device == "cuda" else ""))
                    return True
                # _load_model() silently fell back to CPU internally (its own
                # CUDA try/except) — still a "successful" load, just not on
                # the device we asked for.
                if self.model is not None:
                    logger.warning(f"STT requested {device} but landed on {self.device}")
                    return False
                raise RuntimeError("model is None after load")
            except Exception as e:
                logger.error(f"switch_device to {device} failed ({e}); reverting to {prior_device}")
                self.device, self.device_index, self.compute_type = prior_device, prior_index, prior_compute
                try:
                    self._load_model()
                except Exception as e2:
                    logger.error(f"revert load also failed ({e2}); forcing CPU")
                    self.device, self.compute_type = "cpu", "int8"
                    self._load_model()
                return False

    @property
    def is_loaded(self) -> bool:
        """Whether model is currently in VRAM."""
        return self.model is not None

    @property
    def is_ready(self) -> bool:
        """Check if STT is ready."""
        return self.model is not None


def test_stt():
    """Test STT engine."""
    print("\n" + "=" * 60)
    print("NOVA STT ENGINE TEST (Faster-Whisper)")
    print("=" * 60)

    engine = STTEngine()

    if not engine.is_ready:
        print("\nSTT not ready. Check CUDA/model availability.")
        return False

    print(f"\nModel: {engine.model_size}")
    print(f"Device: {engine.device}")
    print(f"Sample rate: {engine.sample_rate}Hz")

    # Test with silence
    print("\n1. Testing with silence (2 seconds)...")
    silence = np.zeros(engine.sample_rate * 2, dtype=np.float32)
    text, info = engine.transcribe(silence)
    print(f"   Result: '{text}' (expected empty)")

    # Test with synthetic speech (if a test file exists)
    test_file = "/tmp/nova_speech.wav"
    import os
    if os.path.exists(test_file):
        print(f"\n2. Testing with recorded speech...")
        text, info = engine.transcribe_file(test_file)
        print(f"   Result: '{text}'")
        print(f"   Processing time: {info.get('processing_time', 0):.2f}s")
        print(f"   RTF: {info.get('rtf', 0):.2f}x")

    print("\nSTT test complete!")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    test_stt()
