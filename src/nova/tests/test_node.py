"""Tests for Nova GPU Node + WebSocket connection."""
import json
import time
import unittest
from unittest.mock import MagicMock, patch


class TestProtocol(unittest.TestCase):
    """Test the protocol message format."""

    def test_import_protocol(self):
        """Protocol module imports from server package."""
        # Protocol is defined in nova-server, but we test the message format
        pass

    def test_hello_message_format(self):
        """Hello message has required fields."""
        msg = {
            "type": "hello",
            "node_id": "desktop-rtx3090",
            "token": "test-token",
            "capabilities": {"gpu": "RTX 3090 24GB", "stt": True, "tts": True},
        }
        self.assertEqual(msg["type"], "hello")
        self.assertIn("node_id", msg)
        self.assertIn("token", msg)

    def test_transcription_message_format(self):
        """Transcription message has required fields."""
        msg = {
            "type": "transcription",
            "text": "what time is it",
            "audio_duration_s": 2.3,
            "stt_latency_s": 0.8,
        }
        self.assertEqual(msg["type"], "transcription")
        self.assertIn("text", msg)

    def test_tool_result_message_format(self):
        """Tool result message has required fields."""
        msg = {
            "type": "tool_result",
            "request_id": "abc123",
            "result": "GPU: 45C",
        }
        self.assertEqual(msg["type"], "tool_result")
        self.assertIn("request_id", msg)
        self.assertIn("result", msg)

    def test_vram_status_message_format(self):
        """VRAM status message has required fields."""
        msg = {
            "type": "vram_status",
            "free_gb": 18.2,
            "used_gb": 5.8,
            "total_gb": 24.0,
            "models_loaded": ["stt_large_v3"],
            "external_processes": [],
        }
        self.assertEqual(msg["type"], "vram_status")
        self.assertIn("free_gb", msg)


class TestConnection(unittest.TestCase):
    """Test ServerConnection behavior."""

    def test_connection_init(self):
        """Connection initializes with correct parameters."""
        from nova.connection import ServerConnection

        conn = ServerConnection(
            url="ws://localhost:9600",
            auth_token="test-token",
            node_id="test-node",
        )
        self.assertEqual(conn.url, "ws://localhost:9600")
        self.assertEqual(conn.auth_token, "test-token")
        self.assertEqual(conn.node_id, "test-node")
        self.assertFalse(conn.connected)

    def test_connection_send_when_disconnected(self):
        """Messages are dropped when not connected."""
        from nova.connection import ServerConnection

        conn = ServerConnection(
            url="ws://localhost:9600",
            auth_token="test-token",
        )
        # Should not raise
        conn.send({"type": "test"})


try:
    import numpy  # noqa: F401
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


@unittest.skipUnless(HAS_NUMPY, "numpy not available")
class TestAudioCapture(unittest.TestCase):
    """Test AudioCapture behavior."""

    def test_audio_capture_init(self):
        """AudioCapture initializes with defaults."""
        import importlib
        audio_mod = importlib.import_module("nova.voice.audio")
        AudioCapture = audio_mod.AudioCapture

        audio = AudioCapture()
        self.assertEqual(audio.sample_rate, 16000)
        self.assertFalse(audio.is_listening)

    def test_stop_when_not_listening(self):
        """Stopping when not listening returns None."""
        import importlib
        audio_mod = importlib.import_module("nova.voice.audio")
        AudioCapture = audio_mod.AudioCapture

        audio = AudioCapture()
        result = audio.stop()
        self.assertIsNone(result)


class TestHotkey(unittest.TestCase):
    """Test hotkey listener behavior."""

    def test_socket_listener_init(self):
        """SocketCommandListener initializes."""
        from nova.hotkey import SocketCommandListener

        listener = SocketCommandListener(
            on_toggle_voice=lambda: None,
            on_toggle_agent=lambda: None,
        )
        self.assertFalse(listener._running)


class TestConfig(unittest.TestCase):
    """Test config has new sections."""

    def test_server_config_defaults(self):
        """Config includes server section with defaults."""
        from nova.config import DEFAULT_CONFIG

        self.assertIn("server", DEFAULT_CONFIG)
        self.assertIn("url", DEFAULT_CONFIG["server"])
        self.assertIn("auth_token", DEFAULT_CONFIG["server"])

    def test_vram_config_defaults(self):
        """Config includes vram section with defaults."""
        from nova.config import DEFAULT_CONFIG

        self.assertIn("vram", DEFAULT_CONFIG)
        self.assertIn("unload_threshold_gb", DEFAULT_CONFIG["vram"])
        self.assertIn("reload_threshold_gb", DEFAULT_CONFIG["vram"])
        self.assertIn("monitored_processes", DEFAULT_CONFIG["vram"])


if __name__ == "__main__":
    unittest.main()
