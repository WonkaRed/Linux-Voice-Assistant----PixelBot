"""
Audio Capture with Voice Activity Detection

Captures audio from microphone, performs VAD, and resampling.
- Native rate: 44.1kHz (AT2020 USB)
- Target rate: 16kHz (Whisper requirement)
- Uses webrtcvad for voice activity detection
"""
import logging
import queue
import threading
from collections import deque
from typing import Optional, Callable

import numpy as np
import pyaudio
import webrtcvad
import librosa

from src import config

logger = logging.getLogger(__name__)


class AudioCapture:
    """Captures audio from microphone with VAD."""

    def __init__(self, callback: Optional[Callable] = None):
        """
        Initialize audio capture.

        Args:
            callback: Optional callback function(audio_chunk) called for each chunk
        """
        self.callback = callback
        self.is_running = False
        self.stream: Optional[pyaudio.Stream] = None
        self.audio_thread: Optional[threading.Thread] = None

        # VAD
        self.vad = webrtcvad.Vad(config.VAD_MODE)

        # Rolling buffer for keyword detection (10 seconds at 16kHz)
        self.keyword_buffer = deque(
            maxlen=int(config.KEYWORD_BUFFER_SECONDS * config.SAMPLE_RATE)
        )

        # Recording buffer (for active transcription mode)
        self.recording_buffer = []
        self.is_recording = False

        # Silence detection
        self.silence_frames = 0
        self.silence_threshold = int(
            config.SILENCE_DURATION * config.DEVICE_SAMPLE_RATE / config.CHUNK_SIZE
        )

        # Speech state
        self.is_speech_active = False

        logger.info("AudioCapture initialized")

    def start(self) -> bool:
        """Start audio capture."""
        if self.is_running:
            logger.warning("AudioCapture already running")
            return True

        try:
            # Initialize PyAudio
            self.pa = pyaudio.PyAudio()

            # Open stream
            self.stream = self.pa.open(
                format=pyaudio.paFloat32,
                channels=config.CHANNELS,
                rate=config.DEVICE_SAMPLE_RATE,
                input=True,
                frames_per_buffer=config.CHUNK_SIZE,
                stream_callback=self._audio_callback,
            )

            self.is_running = True
            self.stream.start_stream()

            logger.info(f"Audio capture started ({config.DEVICE_SAMPLE_RATE}Hz)")
            return True

        except Exception as e:
            logger.error(f"Failed to start audio capture: {e}", exc_info=True)
            return False

    def stop(self) -> bool:
        """Stop audio capture."""
        if not self.is_running:
            return True

        try:
            self.is_running = False

            if self.stream:
                self.stream.stop_stream()
                self.stream.close()

            if self.pa:
                self.pa.terminate()

            logger.info("Audio capture stopped")
            return True

        except Exception as e:
            logger.error(f"Failed to stop audio capture: {e}", exc_info=True)
            return False

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """
        PyAudio callback for audio chunks.

        Args:
            in_data: Audio data bytes
            frame_count: Number of frames
            time_info: Timing information
            status: Stream status

        Returns:
            tuple: (None, pyaudio.paContinue)
        """
        if status:
            logger.warning(f"Audio stream status: {status}")

        # Convert bytes to numpy array
        audio_chunk = np.frombuffer(in_data, dtype=np.float32)

        # Process in separate thread to avoid blocking callback
        threading.Thread(target=self._process_audio_chunk, args=(audio_chunk,)).start()

        return (None, pyaudio.paContinue)

    def _process_audio_chunk(self, audio_chunk: np.ndarray):
        """
        Process an audio chunk.

        Args:
            audio_chunk: Audio data (44.1kHz)
        """
        try:
            # Resample to 16kHz for Whisper
            audio_16k = librosa.resample(
                audio_chunk,
                orig_sr=config.DEVICE_SAMPLE_RATE,
                target_sr=config.SAMPLE_RATE,
            )

            # Add to keyword buffer (always maintains last 10 seconds)
            self.keyword_buffer.extend(audio_16k)

            # VAD check (requires 16-bit PCM)
            audio_16bit = (audio_16k * 32768).astype(np.int16).tobytes()

            # Check if this chunk contains speech
            try:
                is_speech = self.vad.is_speech(audio_16bit, config.SAMPLE_RATE)
            except:
                # VAD can fail on some audio frames, default to True
                is_speech = True

            # Update speech state
            if is_speech:
                self.is_speech_active = True
                self.silence_frames = 0
            else:
                self.silence_frames += 1

                # If silence threshold reached, mark speech as inactive
                if self.silence_frames >= self.silence_threshold:
                    self.is_speech_active = False

            # If actively recording, add to recording buffer
            if self.is_recording:
                self.recording_buffer.extend(audio_16k)

            # Call user callback if provided
            if self.callback:
                self.callback(audio_16k)

        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}", exc_info=True)

    def get_keyword_buffer(self) -> np.ndarray:
        """
        Get the current keyword buffer (last 10 seconds).

        Returns:
            np.ndarray: Audio data (16kHz)
        """
        return np.array(self.keyword_buffer, dtype=np.float32)

    def start_recording(self):
        """Start recording mode (accumulates audio)."""
        logger.info("Recording started")
        self.is_recording = True
        self.recording_buffer = []

    def stop_recording(self) -> np.ndarray:
        """
        Stop recording and return accumulated audio.

        Returns:
            np.ndarray: Recorded audio (16kHz)
        """
        logger.info(f"Recording stopped ({len(self.recording_buffer)} samples)")
        self.is_recording = False

        audio = np.array(self.recording_buffer, dtype=np.float32)
        self.recording_buffer = []

        return audio

    def is_speech_detected(self) -> bool:
        """
        Check if speech is currently active.

        Returns:
            bool: True if speech detected
        """
        return self.is_speech_active

    def get_status(self) -> dict:
        """
        Get audio capture status.

        Returns:
            dict: Status information
        """
        return {
            "running": self.is_running,
            "recording": self.is_recording,
            "speech_active": self.is_speech_active,
            "keyword_buffer_size": len(self.keyword_buffer),
            "recording_buffer_size": len(self.recording_buffer),
            "device_sample_rate": config.DEVICE_SAMPLE_RATE,
            "target_sample_rate": config.SAMPLE_RATE,
        }

    def __del__(self):
        """Cleanup on deletion."""
        if self.is_running:
            self.stop()


# Test function
def test_audio_capture():
    """Test audio capture."""
    print("=== Testing Audio Capture ===\n")

    def audio_callback(chunk):
        """Test callback."""
        rms = np.sqrt(np.mean(chunk ** 2))
        if rms > 0.01:  # Threshold for "loud enough"
            print(f"Audio chunk: {len(chunk)} samples, RMS: {rms:.4f}")

    capture = AudioCapture(callback=audio_callback)

    print("Starting capture...")
    capture.start()

    print(f"Status: {capture.get_status()}\n")
    print("Speak into microphone for 5 seconds...")

    import time
    time.sleep(5)

    print("\nKeyword buffer samples:", len(capture.get_keyword_buffer()))

    print("\nStarting recording mode...")
    capture.start_recording()
    time.sleep(3)

    recorded = capture.stop_recording()
    print(f"Recorded {len(recorded)} samples ({len(recorded)/config.SAMPLE_RATE:.2f}s)")

    capture.stop()
    print("\n✓ Audio capture test complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    test_audio_capture()
