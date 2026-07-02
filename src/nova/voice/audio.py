"""
Audio capture — microphone input via a subprocess recorder.

Records raw 16 kHz mono s16le PCM from the system audio server (arecord →
parec → ffmpeg, whichever exists). No PortAudio dependency, which keeps the
install free of system dev packages and works cleanly on PipeWire.
"""
import logging
import shutil
import subprocess
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MIN_SAMPLES = 8000  # 0.5s at 16 kHz

# Each builder yields a command that streams raw s16le mono PCM to stdout.
_RECORDERS = [
    ("arecord", lambda sr: ["arecord", "-q", "-f", "S16_LE", "-r", str(sr), "-c", "1", "-t", "raw"]),
    ("parec", lambda sr: ["parec", f"--rate={sr}", "--channels=1", "--format=s16le"]),
    ("ffmpeg", lambda sr: ["ffmpeg", "-hide_banner", "-loglevel", "error",
                           "-f", "pulse", "-i", "default", "-ar", str(sr), "-ac", "1", "-f", "s16le", "-"]),
]


class AudioCapture:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._proc: Optional[subprocess.Popen] = None
        self._buf = bytearray()
        self._reader: Optional[threading.Thread] = None
        self._listening = False
        self._lock = threading.Lock()
        self._cmd = self._pick_recorder()

    def _pick_recorder(self):
        for name, build in _RECORDERS:
            if shutil.which(name):
                logger.info("Audio recorder: %s", name)
                return build(self.sample_rate)
        raise RuntimeError("No audio recorder found (need arecord, parec, or ffmpeg)")

    @property
    def is_listening(self) -> bool:
        return self._listening

    def start(self) -> bool:
        with self._lock:
            if self._listening:
                return True
            try:
                self._buf = bytearray()
                self._proc = subprocess.Popen(
                    self._cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
                )
                self._listening = True
                self._reader = threading.Thread(target=self._read, name="audio-read", daemon=True)
                self._reader.start()
                logger.info("Audio capture started")
                return True
            except Exception as e:
                logger.error("Audio capture failed: %s", e)
                self._cleanup()
                return False

    def _read(self) -> None:
        stream = self._proc.stdout if self._proc else None
        if stream is None:
            return
        try:
            while self._listening:
                chunk = stream.read(4096)
                if not chunk:
                    break
                with self._lock:
                    self._buf.extend(chunk)
        except Exception:
            pass

    def get_buffer_copy(self) -> Optional[np.ndarray]:
        """Snapshot the audio so far without stopping (for streaming STT)."""
        with self._lock:
            if not self._buf:
                return None
            return self._to_float32(bytes(self._buf))

    def stop(self) -> Optional[np.ndarray]:
        """Stop and return float32 audio, or None if too short."""
        with self._lock:
            if not self._listening:
                return None
            self._listening = False
        self._terminate()
        if self._reader:
            self._reader.join(timeout=1)
        with self._lock:
            data = bytes(self._buf)
            self._buf = bytearray()

        audio = self._to_float32(data)
        if len(audio) < MIN_SAMPLES:
            logger.warning("Recording too short (%d samples)", len(audio))
            return None
        logger.info("Audio captured: %.1fs", len(audio) / self.sample_rate)
        return audio

    def _to_float32(self, data: bytes) -> np.ndarray:
        if len(data) < 2:
            return np.array([], dtype=np.float32)
        if len(data) % 2:
            data = data[:-1]  # drop a trailing half-sample
        return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    def _terminate(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    def _cleanup(self) -> None:
        self._terminate()
        self._listening = False
        self._buf = bytearray()
