"""
Text-to-Speech Engine - Piper TTS for Nova/Pixel Bot voice.

Features:
- High-quality neural TTS via Piper
- Streaming audio synthesis
- Async playback support
- Interruptible speech
"""
import logging
import subprocess
import threading
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default voice model path
DEFAULT_VOICE_MODEL = Path(__file__).parent.parent.parent.parent / "models" / "piper" / "en_US-ryan-high.onnx"


class TTSEngine:
    """Text-to-speech engine using Piper."""

    def __init__(self, voice_model: Optional[str] = None):
        """
        Initialize TTS engine.

        Args:
            voice_model: Path to Piper voice model (.onnx file)
        """
        self.voice = None
        self.sample_rate = 22050
        self.current_process: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()  # Reentrant lock to avoid deadlock in _play_audio -> stop()

        # Determine voice model path
        if voice_model:
            self.voice_path = Path(voice_model)
        else:
            self.voice_path = DEFAULT_VOICE_MODEL

        self._load_voice()

    def _load_voice(self):
        """Load the Piper voice model."""
        try:
            from piper import PiperVoice

            if not self.voice_path.exists():
                logger.error(f"Voice model not found: {self.voice_path}")
                logger.error("Voice model missing. Check models/piper/ directory.")
                return

            logger.info(f"Loading Piper voice: {self.voice_path.name}")
            self.voice = PiperVoice.load(str(self.voice_path))
            self.sample_rate = self.voice.config.sample_rate

            logger.info(f"TTS engine ready (sample rate: {self.sample_rate}Hz)")

        except ImportError:
            logger.error("piper-tts not installed. Install with: pip install piper-tts")
        except Exception as e:
            logger.error(f"Failed to load TTS voice: {e}")

    def speak(self, text: str, blocking: bool = True) -> bool:
        """
        Synthesize and play speech.

        Args:
            text: Text to speak
            blocking: Wait for speech to finish

        Returns:
            bool: True if successful
        """
        if not self.voice:
            logger.warning("TTS voice not loaded")
            return False

        if not text or not text.strip():
            return False

        try:
            # Synthesize audio
            logger.info(f"Speaking: '{text[:50]}{'...' if len(text) > 50 else ''}'")

            audio_chunks = list(self.voice.synthesize(text))
            audio_bytes = b''.join([chunk.audio_int16_bytes for chunk in audio_chunks])

            # Save to temp file
            temp_file = Path("/tmp/nova_speech.wav")
            with wave.open(str(temp_file), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(self.sample_rate)
                wav.writeframes(audio_bytes)

            # Play audio
            return self._play_audio(temp_file, blocking=blocking)

        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return False

    def _play_audio(self, audio_path: Path, blocking: bool = True) -> bool:
        """
        Play audio file.

        Args:
            audio_path: Path to audio file
            blocking: Wait for playback to finish

        Returns:
            bool: True if successful
        """
        try:
            with self._lock:
                # Stop any current playback
                self.stop()

                # Start new playback
                self.current_process = subprocess.Popen(
                    ["aplay", "-q", str(audio_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            if blocking:
                self.current_process.wait()
                self.current_process = None

            return True

        except FileNotFoundError:
            logger.error("aplay not found. Install with: sudo apt install alsa-utils")
            return False
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
            return False

    def speak_async(self, text: str) -> bool:
        """
        Speak text asynchronously (non-blocking).

        Args:
            text: Text to speak

        Returns:
            bool: True if started
        """
        thread = threading.Thread(target=self.speak, args=(text, True), daemon=True)
        thread.start()
        return True

    def stop(self):
        """Stop current speech immediately."""
        with self._lock:
            if self.current_process and self.current_process.poll() is None:
                logger.debug("Stopping speech")
                try:
                    self.current_process.terminate()
                    self.current_process.wait(timeout=0.5)
                except:
                    self.current_process.kill()
                self.current_process = None

    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        return self.current_process is not None and self.current_process.poll() is None

    def load(self) -> bool:
        """Load voice model. Returns True if successful."""
        if self.voice is not None:
            return True
        try:
            self._load_voice()
            return self.voice is not None
        except Exception as e:
            logger.error(f"Voice load failed: {e}")
            return False

    def unload(self):
        """Unload voice model."""
        if self.voice is None:
            return
        logger.info("Unloading TTS voice...")
        del self.voice
        self.voice = None
        import gc
        gc.collect()
        logger.info("TTS voice unloaded")

    @property
    def is_loaded(self) -> bool:
        """Whether voice model is currently loaded."""
        return self.voice is not None

    @property
    def is_ready(self) -> bool:
        """Check if TTS is ready."""
        return self.voice is not None


def test_tts():
    """Test TTS engine."""
    print("\n" + "=" * 60)
    print("NOVA TTS ENGINE TEST")
    print("=" * 60)

    engine = TTSEngine()

    if not engine.is_ready:
        print("\nTTS not ready. Check voice model path.")
        return False

    print(f"\nVoice: {engine.voice_path.name}")
    print(f"Sample rate: {engine.sample_rate}Hz")

    print("\n1. Testing basic speech...")
    engine.speak("Welcome aboard captain. All systems online.")

    print("\n2. Testing longer phrase...")
    engine.speak("Detecting multiple leviathan class lifeforms in the region. Are you certain whatever you're doing is worth it?")

    print("\n3. Testing async speech...")
    engine.speak_async("This is asynchronous speech playing in the background.")

    import time
    time.sleep(4)

    print("\nTTS test complete!")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    test_tts()
