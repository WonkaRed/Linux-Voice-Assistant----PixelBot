"""
GPU-aware STT device switching.

Watches VRAM headroom on all GPUs and moves the Whisper model onto a GPU when
there's comfortable room, back to CPU the moment that room disappears. Off by
default (voice.gpu_dynamic.enabled) — this is an opt-in capability, not a
silent default, and it must never contend with anything else on the GPUs.

Design:
- Two polling cadences, not one: fast while resident on a GPU (so an eviction
  reacts quickly if another process needs the room), slow while on CPU
  (so a maxed-out GPU isn't re-checked constantly for no benefit).
- A threshold gap between "safe to load" and "must unload" (hysteresis), on
  top of the cadence difference, so a single noisy reading can't cause a
  flap in either direction.
- Every switch attempt is made while holding the SAME lock the streaming
  transcriber holds during an in-flight chunk (passed in by the caller) —
  so a switch either happens instantly (idle) or waits the bounded duration
  of the current chunk's transcription, never corrupting it. No separate
  "is it idle" polling is needed; the lock itself provides correct ordering.
- Uses pynvml (a direct driver call) rather than shelling out to nvidia-smi,
  so polling even every ~10s is not meaningfully "spamming" anything.
- Any unexpected error forces an immediate, hard fallback to CPU — this
  watcher is never allowed to leave STT in a broken or ambiguous state.
"""
import logging
import threading
import time
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

_pynvml = None
_pynvml_broken = False


def _nvml():
    """Lazy-init pynvml once; if the driver/library is ever unavailable,
    remember that and stop trying (fail safe to 'no GPU info available')."""
    global _pynvml, _pynvml_broken
    if _pynvml_broken:
        return None
    if _pynvml is None:
        try:
            import pynvml
            pynvml.nvmlInit()
            _pynvml = pynvml
        except Exception as e:
            logger.warning(f"pynvml unavailable ({e}) — GPU-dynamic STT disabled")
            _pynvml_broken = True
            return None
    return _pynvml


def gpu_free_mb(index: int) -> Optional[float]:
    """Free VRAM on one GPU in MB, or None if it can't be read."""
    nvml = _nvml()
    if nvml is None:
        return None
    try:
        handle = nvml.nvmlDeviceGetHandleByIndex(index)
        return nvml.nvmlDeviceGetMemoryInfo(handle).free / 1e6
    except Exception as e:
        logger.warning(f"GPU {index} query failed: {e}")
        return None


def gpu_count() -> int:
    nvml = _nvml()
    if nvml is None:
        return 0
    try:
        return nvml.nvmlDeviceGetCount()
    except Exception:
        return 0


def best_gpu(min_free_mb: float, allowed_gpus: Optional[list] = None) -> Optional[int]:
    """Index of the GPU with the most free VRAM among ``allowed_gpus`` that
    meets the threshold.

    ``allowed_gpus`` restricts which GPUs STT may ever land on. It defaults to
    ``[1]`` — GPU 0 drives the desktop display, so putting the STT model there
    risks starving the compositor of VRAM (and crashing GUI windows), and the
    Q8 heretic + RVC voice already share GPU 1. Cole's rule: prefer GPU 1, never
    GPU 0. Pass an explicit list to override.
    """
    if allowed_gpus is None:
        allowed_gpus = [1]
    n = gpu_count()
    best_idx, best_free = None, -1.0
    for i in allowed_gpus:
        if not (0 <= i < n):
            continue
        free = gpu_free_mb(i)
        if free is not None and free > best_free:
            best_idx, best_free = i, free
    if best_idx is not None and best_free >= min_free_mb:
        return best_idx
    return None


class GPUWatcher:
    """
    Background watcher that moves an STTEngine between CPU and GPU based on
    VRAM headroom. See module docstring for the full design rationale.
    """

    def __init__(
        self,
        stt_engine,
        switch_lock: threading.Lock,
        load_threshold_mb: float = 6144,
        unload_threshold_mb: float = 3072,
        active_poll_s: float = 12.0,
        cooldown_poll_s: float = 300.0,
        gpu_compute_type: str = "float16",
        allowed_gpus: Optional[list] = None,
        on_switch: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Args:
            stt_engine: the STTEngine to move between devices.
            switch_lock: the SAME lock the caller uses to guard transcribe()
                calls (e.g. VoiceBridge's _stt_lock) — required, not optional,
                so a switch can never race an in-flight transcription.
            load_threshold_mb: minimum free VRAM required before moving onto
                a GPU. Should include real headroom beyond the model's own
                footprint (~2.7-3.6GB measured for large-v3-turbo/float16),
                not just "technically enough."
            unload_threshold_mb: free VRAM below which we evict back to CPU.
                Deliberately lower than load_threshold_mb — the gap between
                the two is the hysteresis band that (together with the
                cadence difference below) stops rapid flapping.
            active_poll_s: how often to re-check while resident on a GPU.
                Kept short (default 12s) because eviction needs to react
                promptly if something else needs the room.
            cooldown_poll_s: how often to re-check while on CPU (default
                300s / 5 min) — deliberately long, since a maxed-out GPU
                usually stays maxed for a while and there's no upside to
                checking more often.
            gpu_compute_type: compute_type to use when resident on GPU
                (float16 is the correct choice for CUDA; CPU always uses the
                engine's existing int8 setting via switch_device's default).
            on_switch: optional callback(direction, detail) fired after every
                successful switch — "gpu"/"cpu" and a short human string —
                for logging/notifications. Never raises into the watcher.
        """
        self.stt = stt_engine
        self.lock = switch_lock
        self.load_threshold_mb = load_threshold_mb
        self.unload_threshold_mb = unload_threshold_mb
        self.active_poll_s = active_poll_s
        self.cooldown_poll_s = cooldown_poll_s
        self.gpu_compute_type = gpu_compute_type
        # STT may only ever land on these GPUs. Default [1]: never the display
        # GPU 0 (whose VRAM the desktop compositor needs), and GPU 1 already
        # hosts Q8 + the RVC voice, so STT loads there only when there's real
        # room (see load_threshold_mb) and evicts the moment it gets tight.
        self.allowed_gpus = [1] if allowed_gpus is None else list(allowed_gpus)
        self.on_switch = on_switch or (lambda *a: None)

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="gpu-watcher", daemon=True)
        self._thread.start()
        logger.info(
            f"GPU watcher started (load>={self.load_threshold_mb:.0f}MB, "
            f"unload<{self.unload_threshold_mb:.0f}MB, "
            f"active_poll={self.active_poll_s:.0f}s, cooldown_poll={self.cooldown_poll_s:.0f}s)"
        )

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self) -> None:
        while self._running:
            interval = self.active_poll_s if self.stt.device == "cuda" else self.cooldown_poll_s
            # Sleep in small increments so stop() doesn't have to wait out a
            # full 5-minute cooldown interval.
            waited = 0.0
            while waited < interval and self._running:
                step = min(1.0, interval - waited)
                time.sleep(step)
                waited += step
            if not self._running:
                break
            try:
                self._check_and_switch()
            except Exception as e:
                # This watcher must never crash silently into "stuck on GPU."
                logger.error(f"GPU watcher error, forcing CPU as a safety fallback: {e}")
                try:
                    with self.lock:
                        self.stt.switch_device("cpu")
                except Exception as e2:
                    logger.error(f"even the safety fallback to CPU failed: {e2}")

    def _check_and_switch(self) -> None:
        if self.stt.device != "cuda":
            idx = best_gpu(self.load_threshold_mb, self.allowed_gpus)
            if idx is None:
                return  # stay on CPU, nothing to do
            with self.lock:
                # Re-check inside the lock: the world may have moved between
                # the check above and actually acquiring it a moment later.
                idx = best_gpu(self.load_threshold_mb, self.allowed_gpus)
                if idx is None or self.stt.device == "cuda":
                    return
                if self.stt.switch_device("cuda", device_index=idx, compute_type=self.gpu_compute_type):
                    self.on_switch("gpu", f"GPU {idx}")
        else:
            free = gpu_free_mb(self.stt.device_index)
            # A failed/unavailable reading is treated as "not safe" — evict.
            if free is not None and free >= self.unload_threshold_mb:
                return  # still comfortable margin, stay put
            with self.lock:
                if self.stt.device != "cuda":
                    return
                free = gpu_free_mb(self.stt.device_index)
                if free is not None and free >= self.unload_threshold_mb:
                    return
                if self.stt.switch_device("cpu"):
                    reason = "margin gone" if free is not None else "GPU unreadable"
                    self.on_switch("cpu", reason)
