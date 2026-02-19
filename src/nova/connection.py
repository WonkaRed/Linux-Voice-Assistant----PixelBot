"""
Nova WebSocket Connection — Client connection to Nova Server.

Handles:
- Threaded WebSocket client with auto-reconnect
- Token authentication
- Message dispatch via callbacks
- Outgoing message queue
"""
import json
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ServerConnection:
    """
    WebSocket client connection to Nova Server.

    Runs in a background thread with auto-reconnect.
    """

    def __init__(
        self,
        url: str,
        auth_token: str,
        node_id: str = "desktop-rtx3090",
        capabilities: Optional[Dict[str, Any]] = None,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_connected: Optional[Callable] = None,
        on_disconnected: Optional[Callable] = None,
        reconnect_max_delay: float = 30.0,
    ):
        self.url = url
        self.auth_token = auth_token
        self.node_id = node_id
        self.capabilities = capabilities or {
            "gpu": "RTX 3090 24GB",
            "stt": True,
            "tts": True,
        }

        self.on_message = on_message
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.reconnect_max_delay = reconnect_max_delay

        self._ws = None
        self._running = False
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._send_queue: queue.Queue = queue.Queue()
        self._send_thread: Optional[threading.Thread] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self):
        """Start connection in background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._connect_loop, daemon=True)
        self._thread.start()
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._send_thread.start()
        logger.info(f"Connection manager started: {self.url}")

    def stop(self):
        """Stop connection and threads."""
        self._running = False
        self._send_queue.put(None)  # Unblock send loop

        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        if self._thread:
            self._thread.join(timeout=3.0)
        if self._send_thread:
            self._send_thread.join(timeout=2.0)

    def send(self, data: Dict[str, Any]):
        """Queue a message for sending."""
        if self._connected:
            self._send_queue.put(json.dumps(data))
        else:
            logger.debug("Not connected, message dropped")

    def send_raw(self, raw: str):
        """Queue a raw JSON string for sending."""
        if self._connected:
            self._send_queue.put(raw)

    def _connect_loop(self):
        """Main connection loop with auto-reconnect."""
        delay = 1.0

        while self._running:
            try:
                self._connect_and_listen()
                delay = 1.0  # Reset on successful connection
            except Exception as e:
                if not self._running:
                    break
                logger.warning(f"Connection lost: {e}. Reconnecting in {delay:.0f}s...")
                self._set_disconnected()
                time.sleep(delay)
                delay = min(delay * 2, self.reconnect_max_delay)

    def _connect_and_listen(self):
        """Establish connection and listen for messages."""
        from websockets.sync.client import connect

        logger.info(f"Connecting to {self.url}...")

        self._ws = connect(self.url)

        try:
            # Send hello (auth)
            hello = json.dumps({
                "type": "hello",
                "node_id": self.node_id,
                "token": self.auth_token,
                "capabilities": self.capabilities,
            })
            self._ws.send(hello)

            # Wait for welcome
            raw = self._ws.recv(timeout=10)
            data = json.loads(raw)

            if data.get("type") == "error":
                raise ConnectionError(f"Server rejected: {data.get('message')}")

            if data.get("type") != "welcome":
                raise ConnectionError(f"Unexpected response: {data.get('type')}")

            # Connected!
            self._connected = True
            logger.info(f"Connected to Nova Server (session={data.get('session_id')})")

            if self.on_connected:
                self.on_connected()

            # Listen for messages
            for raw in self._ws:
                if not self._running:
                    break

                try:
                    data = json.loads(raw)
                    msg_type = data.get("type")

                    if msg_type == "ping":
                        self._ws.send(json.dumps({"type": "pong"}))
                    elif self.on_message:
                        self.on_message(data)

                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from server")
                except Exception as e:
                    logger.error(f"Message handler error: {e}")

        finally:
            self._set_disconnected()
            try:
                self._ws.close()
            except Exception:
                pass

    def _send_loop(self):
        """Background thread for sending queued messages."""
        while self._running:
            try:
                raw = self._send_queue.get(timeout=1.0)
                if raw is None:
                    break
                if self._connected and self._ws:
                    self._ws.send(raw)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Send error: {e}")

    def _set_disconnected(self):
        """Mark as disconnected and notify."""
        if self._connected:
            self._connected = False
            if self.on_disconnected:
                self.on_disconnected()
