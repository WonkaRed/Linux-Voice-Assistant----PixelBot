"""Tests for VRAM Monitor."""
import unittest
from unittest.mock import MagicMock, patch


class TestVRAMState(unittest.TestCase):
    """Test VRAM state enum."""

    def test_states_exist(self):
        from nova.vram import VRAMState

        self.assertEqual(VRAMState.LOADING.value, "loading")
        self.assertEqual(VRAMState.LOADED.value, "loaded")
        self.assertEqual(VRAMState.ACTIVE.value, "active")
        self.assertEqual(VRAMState.UNLOADING.value, "unloading")
        self.assertEqual(VRAMState.YIELDED.value, "yielded")


class TestVRAMStatus(unittest.TestCase):
    """Test VRAMStatus dataclass."""

    def test_to_dict(self):
        from nova.vram import VRAMStatus

        status = VRAMStatus(
            free_gb=18.2,
            used_gb=5.8,
            total_gb=24.0,
            processes=[{"pid": 1234, "name": "python", "vram_mb": 5800}],
        )
        d = status.to_dict()
        self.assertEqual(d["free_gb"], 18.2)
        self.assertEqual(d["used_gb"], 5.8)
        self.assertEqual(d["total_gb"], 24.0)
        self.assertEqual(len(d["processes"]), 1)


class TestVRAMMonitor(unittest.TestCase):
    """Test VRAMMonitor behavior."""

    def test_init_without_nvml(self):
        """Monitor initializes gracefully without pynvml."""
        with patch.dict('sys.modules', {'pynvml': None}):
            from nova.vram import VRAMMonitor
            # Force reimport to test import failure path
            monitor = VRAMMonitor.__new__(VRAMMonitor)
            monitor.device_index = 0
            monitor.unload_threshold_gb = 4.0
            monitor.reload_threshold_gb = 8.0
            monitor.poll_interval_s = 1.0
            monitor.hysteresis_s = 10.0
            monitor.monitored_processes = ["comfyui"]
            monitor.on_pressure_detected = None
            monitor.on_pressure_relieved = None
            monitor._handle = None
            monitor._running = False
            monitor._thread = None
            monitor._last_state_change = 0.0
            monitor._nova_pid = 1
            monitor._nvml_available = False
            monitor._last_status = None

            self.assertFalse(monitor.is_available)
            self.assertIsNone(monitor.get_status())

    @patch('nova.vram.VRAMMonitor._init_nvml')
    def test_state_transitions(self, mock_init):
        """State transitions are tracked."""
        from nova.vram import VRAMMonitor, VRAMState

        monitor = VRAMMonitor()
        self.assertEqual(monitor.state, VRAMState.LOADED)

        monitor.state = VRAMState.ACTIVE
        self.assertEqual(monitor.state, VRAMState.ACTIVE)

        monitor.state = VRAMState.YIELDED
        self.assertEqual(monitor.state, VRAMState.YIELDED)

    @patch('nova.vram.VRAMMonitor._init_nvml')
    def test_no_unload_during_active(self, mock_init):
        """Should not trigger pressure during ACTIVE state."""
        from nova.vram import VRAMMonitor, VRAMState

        callback = MagicMock()
        monitor = VRAMMonitor(on_pressure_detected=callback)
        monitor.state = VRAMState.ACTIVE

        monitor._check_pressure()
        callback.assert_not_called()

    @patch('nova.vram.VRAMMonitor._init_nvml')
    def test_hysteresis(self, mock_init):
        """Can't reload immediately after state change."""
        from nova.vram import VRAMMonitor
        import time

        monitor = VRAMMonitor(hysteresis_s=10.0)
        monitor._nvml_available = True
        monitor._last_state_change = time.time()  # Just changed

        # Mock get_status to return plenty of free VRAM
        mock_status = MagicMock()
        mock_status.free_gb = 20.0
        monitor.get_status = MagicMock(return_value=mock_status)

        self.assertFalse(monitor.can_reload())


if __name__ == "__main__":
    unittest.main()
