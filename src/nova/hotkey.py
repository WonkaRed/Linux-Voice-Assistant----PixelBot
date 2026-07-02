"""
Hotkey listeners — evdev keyboard + Unix-socket IPC.

Two agents, one key each (default F4 = pixelbot, F8 = jailbreak). On Wayland
the compositor owns the function keys, so the primary path is the Unix socket:
COSMIC runs `nova-toggle <agent>` which pokes the socket. evdev is a best-effort
fallback for environments where we can read the keyboard directly.
"""
import logging
import os
import socket
import threading
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

DEBUG = os.environ.get("NOVA_DEBUG", "").lower() in ("1", "true", "yes")
SOCKET_PATH = os.environ.get("NOVA_SOCKET", "/tmp/nova-voice.sock")


class SocketCommandListener:
    """
    Listen for toggle commands over a Unix socket (Wayland-compatible).

    A command is an agent name (e.g. "pixelbot", "jailbreak") which toggles that
    agent's recording, plus the control words "stop", "status", "ping".
    """

    def __init__(self, on_toggle: Callable[[str], None], agents: list):
        self.on_toggle = on_toggle
        self.agents = set(agents)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None
        self._socket_path = SOCKET_PATH

    def start(self) -> bool:
        try:
            if os.path.exists(self._socket_path):
                os.unlink(self._socket_path)

            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.bind(self._socket_path)
            self._socket.listen(5)
            self._socket.settimeout(0.5)
            os.chmod(self._socket_path, 0o600)

            self._running = True
            self._thread = threading.Thread(target=self._loop, name="socket", daemon=True)
            self._thread.start()
            logger.info("Socket listener: %s", self._socket_path)
            return True
        except Exception as e:
            logger.error("Socket listener failed: %s", e)
            return False

    def _loop(self) -> None:
        while self._running:
            try:
                conn, _ = self._socket.accept()
                conn.settimeout(1.0)
                try:
                    data = conn.recv(256).decode("utf-8").strip().lower()
                    if data in self.agents:
                        self.on_toggle(data)
                        conn.sendall(f"OK: {data} toggled\n".encode())
                    elif data == "stop":
                        self.on_toggle("__stop__")
                        conn.sendall(b"OK: stop\n")
                    elif data == "status":
                        conn.sendall(b"OK: nova running\n")
                    elif data == "ping":
                        conn.sendall(b"pong\n")
                    else:
                        conn.sendall(
                            f"ERROR: unknown command '{data}' (agents: {', '.join(sorted(self.agents))})\n".encode()
                        )
                except socket.timeout:
                    pass
                finally:
                    conn.close()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running and DEBUG:
                    logger.warning("Socket error: %s", e)

    def stop(self) -> None:
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        if os.path.exists(self._socket_path):
            try:
                os.unlink(self._socket_path)
            except Exception:
                pass


class HotkeyListener:
    """evdev fallback: map keycodes to agent toggles (best-effort, X11/root)."""

    def __init__(self, keymap: Dict[str, str], on_toggle: Callable[[str], None]):
        # keymap: {"KEY_F4": "pixelbot", "KEY_F8": "jailbreak"}
        self.keymap = keymap
        self.on_toggle = on_toggle
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._device = None

    def start(self) -> bool:
        try:
            import evdev
            from evdev import ecodes

            wanted_codes = {getattr(ecodes, name) for name in self.keymap if hasattr(ecodes, name)}
            candidates = []
            for path in evdev.list_devices():
                try:
                    dev = evdev.InputDevice(path)
                    caps = set(dev.capabilities().get(ecodes.EV_KEY, []))
                    name_lower = dev.name.lower()
                    if not wanted_codes.issubset(caps) or ecodes.KEY_A not in caps:
                        continue
                    if "mouse" in name_lower or "viper" in name_lower:
                        continue
                    score = (100 if "ornata" in name_lower else 0) + (10 if "keyboard" in name_lower else 0)
                    if score:
                        candidates.append((score, dev))
                except Exception:
                    pass

            if not candidates:
                logger.info("No keyboard found for evdev hotkeys")
                return False

            candidates.sort(key=lambda x: x[0], reverse=True)
            self._device = candidates[0][1]
            logger.info("Selected keyboard: %s", self._device.name)

            self._code_to_agent = {
                getattr(ecodes, name): agent
                for name, agent in self.keymap.items()
                if hasattr(ecodes, name)
            }
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="evdev", daemon=True)
            self._thread.start()
            return True
        except PermissionError:
            logger.info("No permission for evdev hotkeys (normal on Wayland)")
            return False
        except Exception as e:
            logger.info("evdev hotkeys unavailable: %s", e)
            return False

    def _loop(self) -> None:
        import select
        from evdev import ecodes

        try:
            while self._running:
                r, _, _ = select.select([self._device.fd], [], [], 0.5)
                if not r:
                    continue
                for event in self._device.read():
                    if not self._running:
                        return
                    if event.type != ecodes.EV_KEY or event.value != 1:
                        continue
                    agent = self._code_to_agent.get(event.code)
                    if agent:
                        self.on_toggle(agent)
        except Exception as e:
            if self._running:
                logger.error("Hotkey error: %s", e)

    def stop(self) -> None:
        self._running = False
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
