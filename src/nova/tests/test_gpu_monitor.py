"""
GPUWatcher behaviour, fully mocked — no real GPU/pynvml dependency, so these
run deterministically anywhere. Covers: load when safe, evict when tight,
hysteresis (never touches GPU without real margin), and the "never corrupt
an in-flight transcription" locking guarantee.
"""
import threading
import time

import nova.gpu_monitor as gpu_monitor
from nova.gpu_monitor import GPUWatcher


class FakeSTT:
    """Mimics STTEngine's device-switching surface without loading a model."""
    def __init__(self):
        self.device = "cpu"
        self.device_index = 0
        self.compute_type = "int8"
        self.switch_calls = []

    def switch_device(self, device, device_index=0, compute_type=None):
        self.switch_calls.append((device, device_index, compute_type))
        self.device = device
        self.device_index = device_index if device == "cuda" else 0
        return True


def _watcher(stt, free_by_gpu, load_mb=6144, unload_mb=3072, active_poll=0.2, cooldown_poll=0.3, on_switch=None):
    """Build a GPUWatcher with gpu_free_mb/best_gpu monkey-patched to fixed values."""
    def fake_gpu_free_mb(index):
        return free_by_gpu.get(index)

    def fake_best_gpu(min_free_mb):
        best_idx, best_free = None, -1.0
        for idx, free in free_by_gpu.items():
            if free is not None and free > best_free:
                best_idx, best_free = idx, free
        return best_idx if best_idx is not None and best_free >= min_free_mb else None

    gpu_monitor.gpu_free_mb = fake_gpu_free_mb
    gpu_monitor.best_gpu = fake_best_gpu
    return GPUWatcher(
        stt, threading.Lock(), load_threshold_mb=load_mb, unload_threshold_mb=unload_mb,
        active_poll_s=active_poll, cooldown_poll_s=cooldown_poll, on_switch=on_switch or (lambda *a: None),
    )


def teardown_module(module):
    # Restore the real functions so later-imported tests aren't left patched.
    import importlib
    importlib.reload(gpu_monitor)


def test_loads_onto_gpu_when_room_is_ample():
    stt = FakeSTT()
    events = []
    w = _watcher(stt, {0: 8000, 1: 2000}, on_switch=lambda d, r: events.append((d, r)))
    w.start()
    time.sleep(0.6)
    w.stop()
    assert stt.device == "cuda"
    assert stt.device_index == 0  # picked the GPU with more free room
    assert events == [("gpu", "GPU 0")]


def test_stays_on_cpu_when_no_gpu_qualifies():
    stt = FakeSTT()
    w = _watcher(stt, {0: 1000, 1: 500})
    w.start()
    time.sleep(0.6)
    w.stop()
    assert stt.device == "cpu"
    assert stt.switch_calls == []


def test_evicts_when_margin_disappears():
    stt = FakeSTT()
    free = {0: 8000}
    events = []
    w = _watcher(stt, free, on_switch=lambda d, r: events.append((d, r)))
    w.start()
    time.sleep(0.4)
    assert stt.device == "cuda"
    free[0] = 500  # something else grabbed the VRAM
    time.sleep(0.5)
    w.stop()
    assert stt.device == "cpu"
    assert events[0] == ("gpu", "GPU 0")
    assert events[-1][0] == "cpu"


def test_hysteresis_gap_prevents_flap_at_boundary():
    """A reading between unload and load thresholds should not cause a
    reload — that dead zone is the point of having two thresholds."""
    stt = FakeSTT()
    free = {0: 8000}
    w = _watcher(stt, free, load_mb=6144, unload_mb=3072)
    w.start()
    time.sleep(0.4)
    assert stt.device == "cuda"
    free[0] = 4000  # below load threshold, but still above unload threshold
    time.sleep(0.5)
    assert stt.device == "cuda", "should not evict while still above unload_threshold_mb"
    w.stop()


def test_switch_blocks_on_shared_lock_during_inflight_chunk():
    """The watcher must wait for the caller's lock, not switch underneath
    an in-progress transcription."""
    stt = FakeSTT()
    lock = threading.Lock()
    w = GPUWatcher(stt, lock, load_threshold_mb=6144, unload_threshold_mb=3072,
                  active_poll_s=0.1, cooldown_poll_s=0.1)

    def fake_gpu_free_mb(index):
        return 8000
    def fake_best_gpu(min_free_mb):
        return 0
    gpu_monitor.gpu_free_mb = fake_gpu_free_mb
    gpu_monitor.best_gpu = fake_best_gpu

    lock.acquire()  # simulate an in-flight transcription holding the lock
    w.start()
    time.sleep(0.4)
    assert stt.device == "cpu", "must not switch while the transcription lock is held"
    lock.release()
    time.sleep(0.4)
    w.stop()
    assert stt.device == "cuda", "should switch promptly once the lock frees up"


def test_error_during_check_forces_cpu_fallback():
    stt = FakeSTT()

    def boom(min_free_mb):
        raise RuntimeError("simulated nvml failure")
    gpu_monitor.best_gpu = boom
    gpu_monitor.gpu_free_mb = lambda i: None

    w = GPUWatcher(stt, threading.Lock(), active_poll_s=0.1, cooldown_poll_s=0.1)
    stt.device = "cuda"  # pretend we were already resident on a GPU
    w.start()
    time.sleep(0.4)
    w.stop()
    assert stt.device == "cpu", "an unexpected error must never leave STT stuck reporting GPU"
