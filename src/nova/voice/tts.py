"""
Text-to-Speech playback for Nova.

Synthesis is delegated to synth.py (Kokoro / Piper + optional robot effects);
this class owns playback: interruptible, thread-safe, non-blocking option.
The active voice is a catalog entry (see nova.voices), chosen via `nova tts-model`.
"""
import logging
import subprocess
import threading
from typing import Optional

from .synth import synth_to_wav

logger = logging.getLogger(__name__)

_OUT = "/tmp/nova_speech.wav"


class TTSEngine:
    def __init__(self, entry: dict):
        self.entry = entry            # catalog dict: engine/voice/effect/...
        self.current_process: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._synth_lock = threading.Lock()
        if entry:
            logger.info("TTS voice: %s", entry.get("key"))

    @property
    def is_ready(self) -> bool:
        return bool(self.entry)

    def speak(self, text: str, blocking: bool = True) -> bool:
        if not self.entry or not text or not text.strip():
            return False
        try:
            with self._synth_lock:
                synth_to_wav(self.entry, text, _OUT)
            return self._play(_OUT, blocking=blocking)
        except Exception as e:
            logger.error("TTS failed: %s", e)
            return False

    def speak_async(self, text: str) -> bool:
        threading.Thread(target=self.speak, args=(text, True), daemon=True).start()
        return True

    def _play(self, path: str, blocking: bool = True) -> bool:
        try:
            with self._lock:
                self.stop()
                self.current_process = subprocess.Popen(
                    ["aplay", "-q", path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            if blocking:
                self.current_process.wait()
                self.current_process = None
            return True
        except FileNotFoundError:
            logger.error("aplay not found (install alsa-utils)")
            return False
        except Exception as e:
            logger.error("playback failed: %s", e)
            return False

    def stop(self):
        with self._lock:
            if self.current_process and self.current_process.poll() is None:
                try:
                    self.current_process.terminate()
                    self.current_process.wait(timeout=0.5)
                except Exception:
                    try:
                        self.current_process.kill()
                    except Exception:
                        pass
                self.current_process = None

    def is_speaking(self) -> bool:
        return self.current_process is not None and self.current_process.poll() is None
