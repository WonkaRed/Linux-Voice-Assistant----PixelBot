"""
VRAM Monitor — Intelligent GPU memory management.

Monitors VRAM usage and detects external GPU processes (ComfyUI, Blender, etc.)
to trigger model unload/reload for VRAM-submissive behavior.
"""
import logging
import os
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class VRAMState(Enum):
    LOADING = "loading"
    LOADED = "loaded"
    ACTIVE = "active"       # Recording/transcribing in progress
    UNLOADING = "unloading"
    YIELDED = "yielded"     # Models unloaded, GPU yielded to external process


class VRAMStatus:
    """Current VRAM status snapshot."""
    def __init__(self, free_gb: float, used_gb: float, total_gb: float,
                 processes: List[Dict[str, Any]]):
        self.free_gb = free_gb
        self.used_gb = used_gb
        self.total_gb = total_gb
        self.processes = processes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "free_gb": round(self.free_gb, 2),
            "used_gb": round(self.used_gb, 2),
            "total_gb": round(self.total_gb, 2),
            "processes": self.processes,
        }


class VRAMMonitor:
    """
    Monitor GPU VRAM and manage model lifecycle.

    Uses pynvml for direct NVIDIA GPU queries.
    Triggers callbacks when VRAM pressure changes.
    """

    def __init__(
        self,
        device_index: int = 0,
        unload_threshold_gb: float = 4.0,
        reload_threshold_gb: float = 8.0,
        poll_interval_s: float = 1.0,
        hysteresis_s: float = 10.0,
        monitored_processes: Optional[List[str]] = None,
        on_pressure_detected: Optional[Callable] = None,
        on_pressure_relieved: Optional[Callable] = None,
    ):
        self.device_index = device_index
        self.unload_threshold_gb = unload_threshold_gb
        self.reload_threshold_gb = reload_threshold_gb
        self.poll_interval_s = poll_interval_s
        self.hysteresis_s = hysteresis_s
        self.monitored_processes = monitored_processes or [
            "comfyui", "python", "blender", "resolve"
        ]

        self.on_pressure_detected = on_pressure_detected
        self.on_pressure_relieved = on_pressure_relieved

        self._handle = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._state = VRAMState.LOADED
        self._last_state_change = 0.0
        self._nova_pid = os.getpid()
        self._nvml_available = False
        self._last_status: Optional[VRAMStatus] = None

        self._init_nvml()

    def _init_nvml(self):
        """Initialize NVIDIA Management Library."""
        try:
            import pynvml
            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(self.device_index)
            self._nvml_available = True
            name = pynvml.nvmlDeviceGetName(self._handle)
            logger.info(f"VRAM monitor initialized: {name}")
        except ImportError:
            logger.warning("pynvml not installed — VRAM monitoring disabled")
        except Exception as e:
            logger.warning(f"NVML init failed: {e} — VRAM monitoring disabled")

    @property
    def state(self) -> VRAMState:
        return self._state

    @state.setter
    def state(self, new_state: VRAMState):
        if new_state != self._state:
            logger.info(f"VRAM state: {self._state.value} -> {new_state.value}")
            self._state = new_state
            self._last_state_change = time.time()

    def get_status(self) -> Optional[VRAMStatus]:
        """Get current VRAM status."""
        if not self._nvml_available:
            return None

        try:
            import pynvml
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            procs = pynvml.nvmlDeviceGetComputeRunningProcesses(self._handle)

            processes = []
            for p in procs:
                try:
                    name = self._get_process_name(p.pid)
                    processes.append({
                        "pid": p.pid,
                        "name": name,
                        "vram_mb": round(p.usedGpuMemory / 1e6, 1) if p.usedGpuMemory else 0,
                    })
                except Exception:
                    processes.append({
                        "pid": p.pid,
                        "name": "unknown",
                        "vram_mb": round(p.usedGpuMemory / 1e6, 1) if p.usedGpuMemory else 0,
                    })

            status = VRAMStatus(
                free_gb=mem.free / 1e9,
                used_gb=mem.used / 1e9,
                total_gb=mem.total / 1e9,
                processes=processes,
            )
            self._last_status = status
            return status

        except Exception as e:
            logger.error(f"VRAM status check failed: {e}")
            return self._last_status

    def _get_process_name(self, pid: int) -> str:
        """Get process name from PID."""
        try:
            with open(f"/proc/{pid}/comm") as f:
                return f.read().strip()
        except Exception:
            return "unknown"

    def has_external_pressure(self) -> bool:
        """Check if external processes are causing VRAM pressure."""
        status = self.get_status()
        if not status:
            return False

        # Calculate external VRAM usage (not our process)
        external_vram_mb = sum(
            p["vram_mb"] for p in status.processes
            if p["pid"] != self._nova_pid
        )

        # Check if any monitored process is running on GPU
        external_names = [
            p["name"].lower() for p in status.processes
            if p["pid"] != self._nova_pid
        ]
        has_monitored = any(
            monitored in name
            for name in external_names
            for monitored in self.monitored_processes
        )

        return (
            status.free_gb < self.unload_threshold_gb
            and (external_vram_mb > 500 or has_monitored)
        )

    def can_reload(self) -> bool:
        """Check if conditions are safe to reload models."""
        status = self.get_status()
        if not status:
            return False

        # Enough time since last state change (hysteresis)
        if time.time() - self._last_state_change < self.hysteresis_s:
            return False

        return status.free_gb > self.reload_threshold_gb

    def start(self):
        """Start VRAM monitoring thread."""
        if not self._nvml_available:
            logger.info("VRAM monitoring skipped (nvml not available)")
            return

        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("VRAM monitor started")

    def stop(self):
        """Stop VRAM monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                self._check_pressure()
            except Exception as e:
                logger.error(f"VRAM monitor error: {e}")

            time.sleep(self.poll_interval_s)

    def _check_pressure(self):
        """Check VRAM pressure and trigger callbacks."""
        # Don't change state during active recording/transcription
        if self._state == VRAMState.ACTIVE:
            return

        if self._state in (VRAMState.LOADED, VRAMState.LOADING):
            if self.has_external_pressure():
                if self.on_pressure_detected:
                    self.on_pressure_detected()

        elif self._state == VRAMState.YIELDED:
            if self.can_reload():
                if self.on_pressure_relieved:
                    self.on_pressure_relieved()

    @property
    def is_available(self) -> bool:
        return self._nvml_available
