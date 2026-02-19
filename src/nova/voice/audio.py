"""
Audio Capture — Microphone input management.

Extracted from runner.py NovaVoice for clean separation.
"""
import logging
import os
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Minimum recording duration in samples (0.5s at 16kHz)
MIN_SAMPLES = 8000


class AudioCapture:
    """Microphone audio capture with PyAudio."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1,
                 frames_per_buffer: int = 1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frames_per_buffer = frames_per_buffer

        self._pa = None
        self._stream = None
        self._listening = False
        self._audio_buffer = []
        self._lock = threading.Lock()

    @property
    def is_listening(self) -> bool:
        return self._listening

    def start(self) -> bool:
        """Start recording. Returns True if successful."""
        with self._lock:
            if self._listening:
                return True

            try:
                import pyaudio

                # Suppress ALSA/JACK warnings during PyAudio init
                devnull = os.open(os.devnull, os.O_WRONLY)
                old_stderr = os.dup(2)
                os.dup2(devnull, 2)
                try:
                    self._pa = pyaudio.PyAudio()
                finally:
                    os.dup2(old_stderr, 2)
                    os.close(devnull)
                    os.close(old_stderr)

                self._audio_buffer = []

                def callback(in_data, frame_count, time_info, status):
                    if self._listening:
                        self._audio_buffer.append(
                            np.frombuffer(in_data, dtype=np.float32)
                        )
                    return (None, pyaudio.paContinue)

                self._stream = self._pa.open(
                    format=pyaudio.paFloat32,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.frames_per_buffer,
                    stream_callback=callback,
                )

                self._listening = True
                self._stream.start_stream()
                logger.info("Audio capture started")
                return True

            except Exception as e:
                logger.error(f"Audio capture failed: {e}")
                self._cleanup()
                return False

    def stop(self) -> Optional[np.ndarray]:
        """
        Stop recording and return audio data.

        Returns numpy array of float32 audio, or None if recording was too short.
        """
        with self._lock:
            if not self._listening:
                return None

            self._listening = False

            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None

            if self._pa:
                self._pa.terminate()
                self._pa = None

            audio = (
                np.concatenate(self._audio_buffer)
                if self._audio_buffer
                else np.array([], dtype=np.float32)
            )
            self._audio_buffer = []

            if len(audio) < MIN_SAMPLES:
                logger.warning(f"Recording too short ({len(audio)} samples)")
                return None

            duration = len(audio) / self.sample_rate
            logger.info(f"Audio captured: {duration:.1f}s")
            return audio

    def _cleanup(self):
        """Clean up PyAudio resources."""
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

        self._listening = False
        self._audio_buffer = []
