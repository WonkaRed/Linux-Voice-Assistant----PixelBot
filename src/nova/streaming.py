"""
Streaming transcription for long push-to-talk recordings.

On CPU, transcribing a 10-minute take *after* you stop would sit for minutes.
Instead we transcribe the recording in chunks *while* it grows, cutting each
chunk at a silence gap (so we never split a word), and on stop only the short
tail is left to transcribe. The full transcript is the committed chunks + tail —
so even a very long take returns its complete text almost immediately.

This class is pure/synchronous and unit-tested; the threading lives in main.
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)


class StreamingTranscriber:
    def __init__(
        self,
        stt,
        sample_rate: int = 16000,
        chunk_s: float = 15.0,
        silence_search_s: float = 2.0,
        min_tail_s: float = 0.3,
    ):
        self.stt = stt
        self.sr = sample_rate
        self.chunk_samples = int(chunk_s * sample_rate)
        self.search_samples = int(silence_search_s * sample_rate)
        self.min_tail_samples = int(min_tail_s * sample_rate)
        self.reset()

    def reset(self):
        self._committed = 0        # samples already transcribed
        self._texts = []           # committed chunk transcripts, in order

    @property
    def committed_samples(self) -> int:
        return self._committed

    def poll(self, buffer: np.ndarray) -> None:
        """
        Commit any whole chunks now present in ``buffer`` (the full recording so
        far). Called periodically while recording. Cheap when nothing new.
        """
        if buffer is None:
            return
        # Only commit when there's a full chunk plus room to hunt for a silence
        # boundary — this leaves the live edge (possibly mid-word) uncommitted.
        while len(buffer) - self._committed >= self.chunk_samples + self.search_samples:
            target = self._committed + self.chunk_samples
            cut = self._silence_cut(buffer, target)
            chunk = buffer[self._committed:cut]
            self._transcribe_into(chunk)
            self._committed = cut

    def finish(self, buffer: np.ndarray) -> str:
        """Transcribe the remaining tail and return the full transcript."""
        if buffer is not None and len(buffer) - self._committed >= self.min_tail_samples:
            self._transcribe_into(buffer[self._committed:])
            self._committed = len(buffer)
        return " ".join(self._texts).strip()

    # ------------------------------------------------------------------ internals
    def _transcribe_into(self, chunk: np.ndarray) -> None:
        try:
            text, _ = self.stt.transcribe(chunk)
            text = (text or "").strip()
            if text:
                self._texts.append(text)
        except Exception as e:
            logger.error("chunk transcription failed: %s", e)

    def _silence_cut(self, buffer: np.ndarray, target: int) -> int:
        """
        Find the quietest 100 ms spot within ±search of ``target`` and return a
        cut index at its centre, so chunk boundaries land in pauses, not words.
        """
        win = int(0.1 * self.sr)
        lo = max(self._committed + win, target - self.search_samples)
        hi = min(len(buffer) - win, target + self.search_samples)
        if hi <= lo:
            return min(target, len(buffer))
        step = max(1, int(0.02 * self.sr))  # 20 ms hop
        best_idx, best_energy = target, float("inf")
        for start in range(lo, hi, step):
            energy = float(np.abs(buffer[start:start + win]).mean())
            if energy < best_energy:
                best_energy, best_idx = energy, start + win // 2
        return best_idx
