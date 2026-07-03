import numpy as np

from nova.streaming import StreamingTranscriber


class FakeSTT:
    """Records the length of each chunk it's asked to transcribe."""
    def __init__(self):
        self.calls = []

    def transcribe(self, audio):
        self.calls.append(len(audio))
        return (f"seg{len(self.calls)}", {})


def test_short_recording_single_transcribe():
    # Under a chunk: nothing commits during poll; finish does one transcribe.
    stt = FakeSTT()
    st = StreamingTranscriber(stt, sample_rate=16000, chunk_s=15.0)
    buf = np.random.randn(16000 * 8).astype(np.float32) * 0.1  # 8s
    st.poll(buf)
    assert st.committed_samples == 0        # nothing committed yet
    text = st.finish(buf)
    assert text == "seg1"
    assert len(stt.calls) == 1


def test_long_recording_commits_chunks_then_tail():
    stt = FakeSTT()
    st = StreamingTranscriber(stt, sample_rate=16000, chunk_s=15.0, silence_search_s=2.0)
    # 40s of audio → should commit ~2 chunks during poll, tail at finish.
    buf = (np.random.randn(16000 * 40).astype(np.float32) * 0.1)
    st.poll(buf)
    committed_after_poll = len(stt.calls)
    assert committed_after_poll >= 2                 # at least two 15s chunks
    text = st.finish(buf)
    # full transcript is every segment joined in order
    assert text == " ".join(f"seg{i+1}" for i in range(len(stt.calls)))
    # everything got transcribed exactly once, contiguously
    assert sum(stt.calls) == len(buf)


def test_silence_cut_lands_in_the_gap():
    stt = FakeSTT()
    st = StreamingTranscriber(stt, sample_rate=16000, chunk_s=15.0, silence_search_s=2.0)
    # Loud everywhere, with a silent gap straddling the 15s boundary.
    buf = (np.random.randn(16000 * 40).astype(np.float32) * 0.5)
    gap_start = 16000 * 15 + 4000            # just past the 15s target
    buf[gap_start:gap_start + 4800] = 0.0    # 300ms of silence
    st.poll(buf)
    first_chunk_len = stt.calls[0]
    gap_center = gap_start + 2400
    assert abs(first_chunk_len - gap_center) < 2000   # cut within ~125ms of the gap
