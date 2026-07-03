import numpy as np

from nova.streaming import StreamingTranscriber


class FakeSTT:
    """Records the length of each chunk it's asked to transcribe."""
    def __init__(self):
        self.calls = []

    def transcribe(self, audio):
        self.calls.append(len(audio))
        return (f"seg{len(self.calls)}", {})


def _loud(seconds, sr=16000, level=0.3):
    return (np.random.randn(int(seconds * sr)).astype(np.float32) * level)


def _silence(seconds, sr=16000):
    return np.zeros(int(seconds * sr), dtype=np.float32)


def test_short_continuous_defers_to_finish():
    # Under the max chunk, no pause → nothing commits mid-recording.
    stt = FakeSTT()
    st = StreamingTranscriber(stt, chunk_s=9.0)
    buf = _loud(6)
    st.poll(buf)
    assert st.committed_samples == 0
    assert st.finish(buf) == "seg1"
    assert len(stt.calls) == 1


def test_continuous_speech_force_commits_by_max_chunk():
    stt = FakeSTT()
    st = StreamingTranscriber(stt, chunk_s=9.0)
    buf = _loud(30)                      # no silence at all
    st.poll(buf)
    assert len(stt.calls) >= 3           # ~every 9s
    text = st.finish(buf)
    assert text == " ".join(f"seg{i+1}" for i in range(len(stt.calls)))
    assert sum(stt.calls) == len(buf)    # full, contiguous coverage


def test_commits_at_a_pause():
    stt = FakeSTT()
    st = StreamingTranscriber(stt, chunk_s=9.0, min_commit_s=2.0, min_silence_s=0.3)
    buf = np.concatenate([_loud(4), _silence(0.5), _loud(4)])   # pause at 4.0–4.5s
    st.poll(buf)
    assert len(stt.calls) == 1                    # committed the phrase before the pause
    cut = stt.calls[0]
    assert 16000 * 4.0 <= cut <= 16000 * 4.6      # boundary landed inside the pause
    # the trailing phrase is still uncommitted until finish
    st.finish(buf)
    assert len(stt.calls) == 2


def test_full_transcript_preserved_across_commits():
    stt = FakeSTT()
    st = StreamingTranscriber(stt, chunk_s=9.0)
    buf = np.concatenate([_loud(5), _silence(0.4), _loud(12), _silence(0.4), _loud(3)])
    # simulate a growing recording
    step = 16000 * 3
    for end in range(step, len(buf) + step, step):
        st.poll(buf[:min(end, len(buf))])
    st.finish(buf)
    assert sum(stt.calls) == len(buf)    # every sample transcribed exactly once
