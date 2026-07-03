"""
Streaming transcription for push-to-talk — transcribe *while* you speak.

As the recording grows we commit finished speech in the pauses: whenever you
stop for ~half a second, everything up to that pause is transcribed in the
background. So the moment you press stop, only the last (usually short) phrase
is left to transcribe — the full text comes back almost immediately, even for a
ten-minute take. A max-chunk cap force-commits if you talk continuously with no
pause.

Boundaries land in silence, so words are never split. Pure/synchronous and
unit-tested; the threading lives in main.
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)


class StreamingTranscriber:
    def __init__(
        self,
        stt,
        sample_rate: int = 16000,
        chunk_s: float = 9.0,           # force a cut after this much unbroken speech
        min_commit_s: float = 2.0,      # don't commit fragments shorter than this
        min_silence_s: float = 0.3,     # a pause this long is a commit boundary
        silence_thresh: float = 0.02,   # RMS below this (on [-1,1]) counts as silence
        min_tail_s: float = 0.3,
    ):
        self.stt = stt
        self.sr = sample_rate
        self.max_chunk = int(chunk_s * sample_rate)
        self.min_commit = int(min_commit_s * sample_rate)
        self.min_silence = int(min_silence_s * sample_rate)
        self.silence_thresh = silence_thresh
        self.min_tail_samples = int(min_tail_s * sample_rate)
        self._win = int(0.1 * sample_rate)   # 100 ms analysis window
        self._hop = int(0.05 * sample_rate)  # 50 ms hop
        self.reset()

    def reset(self):
        self._committed = 0
        self._texts = []

    @property
    def committed_samples(self) -> int:
        return self._committed

    def poll(self, buffer: np.ndarray) -> None:
        """Commit any speech now bounded by a pause (or the max-chunk cap)."""
        if buffer is None:
            return
        # Keep the live edge (last ~250 ms) uncommitted — you may be mid-word.
        limit = len(buffer) - int(0.25 * self.sr)
        while limit - self._committed >= self.min_commit:
            gap = self._find_silence_gap(buffer, self._committed + self.min_commit, limit)
            if gap is not None:
                self._transcribe_into(buffer[self._committed:gap])
                self._committed = gap
            elif limit - self._committed >= self.max_chunk:
                cut = self._quietest(buffer, self._committed + self.max_chunk)
                self._transcribe_into(buffer[self._committed:cut])
                self._committed = cut
            else:
                break

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

    def _find_silence_gap(self, buffer, start, limit):
        """
        Return a cut index at the middle of the first >= min_silence pause found
        in buffer[start:limit], or None if the speaker hasn't paused yet.
        """
        run_start = None
        i = start
        while i + self._win <= limit:
            quiet = float(np.abs(buffer[i:i + self._win]).mean()) < self.silence_thresh
            if quiet:
                if run_start is None:
                    run_start = i
                if (i + self._win) - run_start >= self.min_silence:
                    return (run_start + i + self._win) // 2
            else:
                run_start = None
            i += self._hop
        return None

    def _quietest(self, buffer, target):
        """Quietest 100 ms spot within ±1s of target (max-chunk fallback cut)."""
        span = int(1.0 * self.sr)
        lo = max(self._committed + self._win, target - span)
        hi = min(len(buffer) - self._win, target + span)
        if hi <= lo:
            return min(target, len(buffer))
        best_idx, best_energy = target, float("inf")
        for start in range(lo, hi, self._hop):
            energy = float(np.abs(buffer[start:start + self._win]).mean())
            if energy < best_energy:
                best_energy, best_idx = energy, start + self._win // 2
        return best_idx
