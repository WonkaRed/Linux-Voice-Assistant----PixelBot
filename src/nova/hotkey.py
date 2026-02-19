"""
Hotkey Listeners — evdev keyboard + Unix socket IPC.

Extracted from runner.py for clean separation.
"""
import logging
import os
import socket
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEBUG = os.environ.get('NOVA_DEBUG', '').lower() in ('1', 'true', 'yes')
SOCKET_PATH = os.environ.get('NOVA_SOCKET', '/tmp/nova-voice.sock')


class HotkeyListener:
    """Hotkey listener using evdev (works on X11, partial Wayland)."""

    def __init__(self, on_f4: Callable, on_super_f4: Callable):
        self.on_f4 = on_f4
        self.on_super_f4 = on_super_f4
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._device = None

    def start(self) -> bool:
        """Start listener. Returns True if successful."""
        try:
            import evdev
            from evdev import ecodes

            candidates = []
            for path in evdev.list_devices():
                try:
                    dev = evdev.InputDevice(path)
                    caps = dev.capabilities().get(ecodes.EV_KEY, [])
                    has_f4 = ecodes.KEY_F4 in caps
                    has_a = ecodes.KEY_A in caps
                    name_lower = dev.name.lower()

                    if not (has_f4 and has_a):
                        continue

                    if "viper" in name_lower or "mouse" in name_lower:
                        continue

                    score = 0
                    if "ornata" in name_lower:
                        score += 100
                    if "keyboard" in name_lower:
                        score += 10

                    if score > 0:
                        candidates.append((score, dev))
                except Exception:
                    pass

            if not candidates:
                logger.info("No keyboard found for hotkeys")
                return False

            candidates.sort(key=lambda x: x[0], reverse=True)
            self._device = candidates[0][1]
            logger.info(f"Selected keyboard: {self._device.name}")

            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return True

        except PermissionError:
            logger.error("No permission for hotkeys. Run: sudo usermod -aG input $USER")
            return False
        except Exception as e:
            logger.error(f"Hotkey init failed: {e}")
            return False

    def _loop(self):
        """Event loop."""
        import select
        from evdev import ecodes
        super_pressed = False

        try:
            while self._running:
                r, _, _ = select.select([self._device.fd], [], [], 0.5)
                if not r:
                    continue

                for event in self._device.read():
                    if not self._running:
                        return
                    if event.type != ecodes.EV_KEY:
                        continue

                    key = event.code
                    pressed = event.value == 1

                    if key in (ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA):
                        super_pressed = pressed
                        continue

                    if key == ecodes.KEY_F4 and pressed:
                        if super_pressed:
                            self.on_super_f4()
                        else:
                            self.on_f4()
        except Exception as e:
            if self._running:
                logger.error(f"Hotkey error: {e}")

    def stop(self):
        """Stop listener."""
        self._running = False
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass


class SocketCommandListener:
    """
    Listen for commands via Unix socket (Wayland-compatible).

    Commands: toggle, voice, agent, stop, status, ping
    """

    def __init__(self, on_toggle_voice: Callable, on_toggle_agent: Callable):
        self.on_toggle_voice = on_toggle_voice
        self.on_toggle_agent = on_toggle_agent
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None
        self._socket_path = SOCKET_PATH

    def start(self) -> bool:
        """Start socket listener."""
        try:
            if os.path.exists(self._socket_path):
                os.unlink(self._socket_path)

            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.bind(self._socket_path)
            self._socket.listen(5)
            self._socket.settimeout(0.5)
            os.chmod(self._socket_path, 0o666)

            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

            logger.info(f"Socket listener: {self._socket_path}")
            return True

        except Exception as e:
            logger.error(f"Socket listener failed: {e}")
            return False

    def _loop(self):
        """Listen for commands."""
        while self._running:
            try:
                conn, _ = self._socket.accept()
                conn.settimeout(1.0)

                try:
                    data = conn.recv(256).decode('utf-8').strip().lower()

                    if data in ('toggle', 'voice', 'f4'):
                        self.on_toggle_voice()
                        conn.sendall(b"OK: voice toggled\n")
                    elif data in ('agent', 'load', 'super+f4'):
                        self.on_toggle_agent()
                        conn.sendall(b"OK: agent toggled\n")
                    elif data == 'stop':
                        conn.sendall(b"OK: stop\n")
                    elif data == 'status':
                        conn.sendall(b"OK: nova running\n")
                    elif data == 'ping':
                        conn.sendall(b"pong\n")
                    else:
                        conn.sendall(f"ERROR: unknown command '{data}'\n".encode())

                except socket.timeout:
                    pass
                finally:
                    conn.close()

            except socket.timeout:
                continue
            except Exception as e:
                if self._running and DEBUG:
                    logger.warning(f"Socket error: {e}")

    def stop(self):
        """Stop listener."""
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
