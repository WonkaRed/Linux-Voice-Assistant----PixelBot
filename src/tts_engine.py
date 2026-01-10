"""
Text-to-Speech Engine

Uses Piper TTS with Subnautica PDA voice for sci-fi aesthetic.
Runs locally via Docker container - no API costs, fully offline.
"""
import logging
import os
import subprocess
import requests
from pathlib import Path
from typing import Optional

from src import config

logger = logging.getLogger(__name__)


class TTSEngine:
    """Text-to-speech engine using Piper TTS (Subnautica PDA voice)."""

    def __init__(self, api_url: str = "http://localhost:5000"):
        """
        Initialize TTS engine.

        Args:
            api_url: URL of the Piper TTS API server
        """
        self.api_url = api_url
        self.is_available = False
        self.current_audio_process = None  # Track playing audio for interruption

        # Check if TTS server is available
        try:
            response = requests.get(self.api_url.replace(":5000", ":5000/health"), timeout=2)
            self.is_available = True
            logger.info("✓ Piper TTS engine initialized (Subnautica PDA voice)")
        except requests.exceptions.ConnectionError:
            # Try a simple POST to see if server responds
            try:
                test_response = requests.post(
                    self.api_url,
                    json={"text": "test"},
                    timeout=2
                )
                self.is_available = True
                logger.info("✓ Piper TTS engine initialized (Subnautica PDA voice)")
            except Exception:
                logger.warning("Piper TTS server not available at " + self.api_url)
                logger.warning("Start with: docker start pda-voice")
                self.is_available = False
        except Exception as e:
            logger.warning(f"Failed to connect to TTS server: {e}")
            self.is_available = False

    def speak(
        self,
        text: str,
        play: bool = True,
    ) -> Optional[Path]:
        """
        Generate and optionally play speech.

        Args:
            text: Text to speak
            play: Whether to play audio immediately

        Returns:
            Path: Path to generated audio file, or None if failed
        """
        if not self.is_available:
            logger.warning("TTS not available, skipping speech")
            return None

        if not text or not text.strip():
            logger.warning("Empty text provided to TTS")
            return None

        try:
            logger.info(f"Generating speech: '{text[:50]}{'...' if len(text) > 50 else ''}'")

            # Send request to Piper TTS API
            response = requests.post(
                self.api_url,
                json={"text": text},
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            # Check if request was successful
            response.raise_for_status()

            # Save to temp file
            output_path = Path(config.TTS_TEMP_FILE)
            output_path.write_bytes(response.content)

            logger.info(f"✓ Speech generated: {output_path}")

            # Play if requested
            if play:
                self.play_audio(output_path)

            return output_path

        except requests.exceptions.ConnectionError:
            logger.error("Could not connect to TTS server. Is Docker container running?")
            logger.error("  Start with: docker start pda-voice")
            return None

        except requests.exceptions.Timeout:
            logger.error("TTS request timed out. Text might be too long.")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"TTS request failed: {e}", exc_info=True)
            return None

        except Exception as e:
            logger.error(f"Failed to generate speech: {e}", exc_info=True)
            return None

    def stop_audio(self):
        """
        Stop currently playing audio immediately.

        Called when user presses F4 to interrupt TTS and start new recording.
        """
        if self.current_audio_process and self.current_audio_process.poll() is None:
            logger.info("Stopping audio playback (interrupted by user)")
            try:
                self.current_audio_process.terminate()
                self.current_audio_process.wait(timeout=0.5)
            except:
                self.current_audio_process.kill()
            self.current_audio_process = None

    def play_audio(self, audio_path: Path) -> bool:
        """
        Play audio file using aplay (WAV format).

        Args:
            audio_path: Path to audio file

        Returns:
            bool: True if successful
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return False

        try:
            # Use Popen instead of run so we can interrupt playback
            self.current_audio_process = subprocess.Popen(
                ["aplay", "-q", str(audio_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for completion
            self.current_audio_process.wait()
            self.current_audio_process = None

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to play audio: {e}")
            return False
        except FileNotFoundError:
            logger.error("aplay not found. Install with: sudo apt install alsa-utils")
            return False
        except Exception as e:
            logger.error(f"Audio playback error: {e}", exc_info=True)
            return False

    def speak_async(self, text: str) -> bool:
        """
        Generate and play speech in background (non-blocking).

        Args:
            text: Text to speak

        Returns:
            bool: True if started successfully
        """
        import threading

        def _speak_thread():
            self.speak(text, play=True)

        try:
            thread = threading.Thread(target=_speak_thread, daemon=True)
            thread.start()
            return True
        except Exception as e:
            logger.error(f"Failed to start async speech: {e}")
            return False


# Test function
def test_tts_engine():
    """Test TTS engine."""
    print("\n" + "=" * 70)
    print("PIPER TTS ENGINE TEST (Subnautica PDA Voice)")
    print("=" * 70)

    engine = TTSEngine()

    if not engine.is_available:
        print("\n⚠️  TTS not available")
        print("    Make sure Docker container is running:")
        print("    docker ps | grep pda-voice")
        print("\n    If not running, start with:")
        print("    docker start pda-voice")
        return False

    print(f"\n✓ TTS engine available")
    print(f"  Voice: Subnautica PDA (custom Piper model)")
    print(f"  API: {engine.api_url}")

    # Test basic speech
    print("\n1. Testing basic speech (PDA voice)...")
    engine.speak("Welcome aboard wonka. All systems online.")

    print("\n2. Testing different phrase...")
    engine.speak("Detecting multiple leviathan class lifeforms in the region. Are you certain whatever you're doing is worth it?")

    print("\n3. Testing async speech...")
    engine.speak_async("This is asynchronous speech. It plays in the background.")

    import time
    time.sleep(3)  # Wait for async speech

    print("\n" + "=" * 70)
    print("✅ TTS ENGINE TEST COMPLETE")
    print("=" * 70)
    print("\nPlease verify you heard the Subnautica PDA voice")
    print()

    return True


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run test
    test_tts_engine()
