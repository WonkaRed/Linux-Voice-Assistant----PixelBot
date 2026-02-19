"""
Voice Interface - Full voice pipeline for Nova agent.

Features:
- Push-to-talk and continuous listening modes
- Real-time speech recognition
- TTS responses via Piper
- Hotkey support (F4 for push-to-talk)
"""
import logging
import queue
import threading
import time
from typing import Optional, Callable

import numpy as np

from .tts import TTSEngine
from .stt import STTEngine

logger = logging.getLogger(__name__)


class VoiceInterface:
    """Voice interface combining STT, agent, and TTS."""

    def __init__(
        self,
        agent=None,
        stt_model: str = "base.en",
        voice_model: Optional[str] = None,
        on_listening: Optional[Callable] = None,
        on_processing: Optional[Callable] = None,
        on_speaking: Optional[Callable] = None,
    ):
        """
        Initialize voice interface.

        Args:
            agent: Nova agent instance (optional, can be set later)
            stt_model: Whisper model size
            voice_model: Path to Piper voice model
            on_listening: Callback when listening starts
            on_processing: Callback when processing starts
            on_speaking: Callback when speaking starts
        """
        self.agent = agent

        # Callbacks for UI updates
        self.on_listening = on_listening
        self.on_processing = on_processing
        self.on_speaking = on_speaking

        # Initialize engines
        logger.info("Initializing voice interface...")
        self.tts = TTSEngine(voice_model=voice_model)
        self.stt = STTEngine(model_size=stt_model)

        # Audio capture state
        self.is_listening = False
        self.audio_buffer = []
        self.audio_queue = queue.Queue()
        self.sample_rate = 16000

        # PyAudio resources
        self.pa = None
        self.stream = None

        logger.info("Voice interface ready")

    def set_agent(self, agent):
        """Set the Nova agent."""
        self.agent = agent

    def start_listening(self) -> bool:
        """
        Start listening for speech.

        Returns:
            bool: True if started successfully
        """
        if self.is_listening:
            return True

        try:
            import pyaudio
            import os
            import sys

            # Suppress ALSA/JACK warnings during PyAudio initialization
            devnull = os.open(os.devnull, os.O_WRONLY)
            old_stderr = os.dup(2)
            os.dup2(devnull, 2)
            os.close(devnull)

            try:
                self.pa = pyaudio.PyAudio()
            finally:
                os.dup2(old_stderr, 2)
                os.close(old_stderr)

            # Open input stream
            self.stream = self.pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=1024,
                stream_callback=self._audio_callback,
            )

            self.is_listening = True
            self.audio_buffer = []
            self.stream.start_stream()

            if self.on_listening:
                self.on_listening(True)

            logger.info("Listening started")
            return True

        except Exception as e:
            logger.error(f"Failed to start listening: {e}")
            return False

    def stop_listening(self) -> np.ndarray:
        """
        Stop listening and return recorded audio.

        Returns:
            np.ndarray: Recorded audio data
        """
        if not self.is_listening:
            return np.array([], dtype=np.float32)

        try:
            self.is_listening = False

            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

            if self.pa:
                self.pa.terminate()
                self.pa = None

            if self.on_listening:
                self.on_listening(False)

            # Return collected audio
            audio = np.concatenate(self.audio_buffer) if self.audio_buffer else np.array([], dtype=np.float32)
            self.audio_buffer = []

            logger.info(f"Listening stopped ({len(audio) / self.sample_rate:.2f}s recorded)")
            return audio

        except Exception as e:
            logger.error(f"Error stopping listening: {e}")
            return np.array([], dtype=np.float32)

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback for audio chunks."""
        import pyaudio

        if self.is_listening:
            audio_chunk = np.frombuffer(in_data, dtype=np.float32)
            self.audio_buffer.append(audio_chunk)

        return (None, pyaudio.paContinue)

    def process_speech(self, audio: np.ndarray) -> str:
        """
        Process recorded speech through the pipeline.

        Args:
            audio: Audio data

        Returns:
            str: Agent response text
        """
        if len(audio) == 0:
            return ""

        # Transcribe
        if self.on_processing:
            self.on_processing("transcribing")

        text, info = self.stt.transcribe(audio)

        if not text or not text.strip():
            logger.info("No speech detected")
            return ""

        logger.info(f"Transcribed: '{text}'")

        # Process with agent
        if self.agent:
            if self.on_processing:
                self.on_processing("thinking")

            response = self.agent.chat(text)

            # Speak response
            if self.on_speaking:
                self.on_speaking(True)

            self.tts.speak(response)

            if self.on_speaking:
                self.on_speaking(False)

            return response
        else:
            logger.warning("No agent configured")
            return text

    def listen_and_respond(self, duration: float = 5.0) -> str:
        """
        Listen for specified duration, then process and respond.

        Args:
            duration: How long to listen (seconds)

        Returns:
            str: Agent response
        """
        self.start_listening()
        time.sleep(duration)
        audio = self.stop_listening()
        return self.process_speech(audio)

    def push_to_talk(self, key: str = "f4"):
        """
        Start push-to-talk mode.

        Hold the specified key to speak, release to process.

        Args:
            key: Hotkey to use (default: F4)
        """
        try:
            from pynput import keyboard

            print(f"\nPush-to-talk mode: Hold {key.upper()} to speak")
            print("Press ESC to exit\n")

            is_recording = False

            def on_press(k):
                nonlocal is_recording
                try:
                    if hasattr(k, 'name') and k.name == key and not is_recording:
                        is_recording = True
                        print("Recording...")
                        self.start_listening()
                except:
                    pass

            def on_release(k):
                nonlocal is_recording
                try:
                    if hasattr(k, 'name') and k.name == key and is_recording:
                        is_recording = False
                        print("Processing...")
                        audio = self.stop_listening()
                        if len(audio) > 0:
                            response = self.process_speech(audio)
                            if response:
                                print(f"\nNova: {response}\n")
                        else:
                            print("No audio captured")

                    elif k == keyboard.Key.esc:
                        return False
                except:
                    pass

            with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                listener.join()

        except ImportError:
            logger.error("pynput not installed. Install with: pip install pynput")

    def interactive_mode(self):
        """
        Interactive voice mode.

        Press Enter to start recording, Enter again to stop and process.
        """
        print("\n" + "=" * 60)
        print("NOVA VOICE INTERFACE - Interactive Mode")
        print("=" * 60)
        print("\nPress Enter to start/stop recording")
        print("Type 'quit' or 'exit' to leave\n")

        while True:
            try:
                input("Press Enter to speak...")

                # Interrupt any current speech
                self.tts.stop()

                print("Listening... (press Enter when done)")
                self.start_listening()

                input()  # Wait for user to press Enter again

                audio = self.stop_listening()

                if len(audio) < self.sample_rate * 0.5:  # Less than 0.5s
                    print("Recording too short, try again\n")
                    continue

                print("Processing...")
                response = self.process_speech(audio)

                if response:
                    print(f"\nNova: {response}\n")

            except KeyboardInterrupt:
                print("\n\nExiting voice mode...")
                break
            except EOFError:
                break

    @property
    def is_ready(self) -> bool:
        """Check if voice interface is ready."""
        return self.stt.is_ready and self.tts.is_ready


def test_voice_interface():
    """Test the voice interface."""
    print("\n" + "=" * 60)
    print("NOVA VOICE INTERFACE TEST")
    print("=" * 60)

    # Create interface without agent (just test audio pipeline)
    interface = VoiceInterface()

    if not interface.is_ready:
        print("\nVoice interface not ready!")
        return False

    print("\nSTT Ready:", interface.stt.is_ready)
    print("TTS Ready:", interface.tts.is_ready)

    # Test TTS
    print("\n1. Testing TTS...")
    interface.tts.speak("Nova voice interface initialized. All systems operational.")

    # Test recording
    print("\n2. Testing audio capture (3 seconds)...")
    interface.start_listening()
    time.sleep(3)
    audio = interface.stop_listening()
    print(f"   Captured {len(audio)} samples ({len(audio) / interface.sample_rate:.2f}s)")

    # Test transcription
    if len(audio) > 0:
        print("\n3. Testing transcription...")
        text, info = interface.stt.transcribe(audio)
        print(f"   Transcribed: '{text}'")

    print("\nVoice interface test complete!")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    test_voice_interface()
