"""
Text-to-Speech playback for Nova.

Synthesis is delegated to synth.py (Kokoro / Piper + optional robot effects);
this class owns playback: interruptible, thread-safe, non-blocking option.
The active voice is a catalog entry (see nova.voices), chosen via `nova tts-model`.
"""
import logging
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from .synth import synth_to_wav

logger = logging.getLogger(__name__)

_OUT = "/tmp/nova_speech.wav"

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _tmp_path(i: int) -> str:
    return f"/tmp/nova_speech_{i}.wav"


def chunk_text(text: str, first_max: int = 90, rest_target: int = 170) -> list:
    """Split a reply into speakable chunks for streaming synthesis.

    The FIRST chunk is kept small (≈one sentence, ``first_max`` chars) so the
    reply starts talking as soon as possible; later chunks are merged up to
    ``rest_target`` chars so they're big enough to synth smoothly while the
    previous chunk is still playing (avoids choppy micro-clips). Falls back to
    the whole text as one chunk when there are no sentence boundaries.
    """
    sents = [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]
    if not sents:
        return [text.strip()] if text.strip() else []
    chunks, cur, target = [], "", first_max
    for s in sents:
        if cur and len(cur) + 1 + len(s) > target:
            chunks.append(cur)
            cur, target = s, rest_target
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


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

    def speak(
        self,
        text: str,
        blocking: bool = True,
        should_continue: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Speak ``text``. For multi-sentence replies this STREAMS: the first
        chunk starts playing while later chunks are still being synthesized, so
        time-to-first-audio is ~one sentence instead of the whole reply. The
        RVC/Kokoro synth of chunk N+1 overlaps the playback of chunk N (playback
        holds no synth lock), which hides most of the CPU synth cost.

        ``should_continue`` is polled before each chunk plays; returning False
        (barge-in / shutdown) stops cleanly without playing the rest.
        """
        if not self.entry or not text or not text.strip():
            return False
        keep = should_continue or (lambda: True)
        chunks = chunk_text(text)
        if not chunks:
            return False

        # Single chunk (short reply): no pipeline needed.
        if len(chunks) == 1:
            try:
                with self._synth_lock:
                    synth_to_wav(self.entry, chunks[0], _OUT)
                if not keep():
                    return True
                return self._play(_OUT, blocking=blocking)
            except Exception as e:
                logger.error("TTS failed: %s", e)
                return False

        # Streaming pipeline: synth chunk 0, then for each chunk kick off the
        # next chunk's synth (background) and play the current one. A 1-worker
        # pool + the synth lock keep synths serialized (the RVC server is
        # single-threaded anyway) while letting a synth run during playback.
        ex = ThreadPoolExecutor(max_workers=1)

        def _synth(i: int) -> Optional[str]:
            try:
                with self._synth_lock:
                    synth_to_wav(self.entry, chunks[i], _tmp_path(i))
                return _tmp_path(i)
            except Exception as e:
                logger.error("TTS chunk %d failed: %s", i, e)
                return None

        try:
            fut = ex.submit(_synth, 0)
            for i in range(len(chunks)):
                path = fut.result()
                if i + 1 < len(chunks):
                    fut = ex.submit(_synth, i + 1)   # synth next while this plays
                if not keep():
                    break
                if path:
                    self._play(path, blocking=True)
            return True
        except Exception as e:
            logger.error("TTS streaming failed: %s", e)
            return False
        finally:
            ex.shutdown(wait=False)

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
