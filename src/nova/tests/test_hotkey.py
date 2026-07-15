import socket
import time

from nova.hotkey import SocketCommandListener


def _recv_all(sock) -> str:
    chunks = []
    while True:
        b = sock.recv(65536)
        if not b:
            break
        chunks.append(b)
    return b"".join(chunks).decode()


def _client(path):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.settimeout(5)
    c.connect(path)
    return c


def test_socket_ask_routes_to_on_ask(tmp_path):
    """`nova ask` -> socket `ask <agent> <text>` -> on_ask -> reply, without
    touching the toggle path (this is what avoids the second Telethon session)."""
    seen = {}
    lis = SocketCommandListener(
        on_toggle=lambda a: seen.setdefault("toggle", a),
        agents=["jailbreak", "pixelbot"],
        on_ask=lambda agent, text: f"got {agent}:{text}",
    )
    lis._socket_path = str(tmp_path / "nova.sock")
    assert lis.start()
    try:
        c = _client(lis._socket_path)
        c.sendall(b"ask jailbreak Hello World")   # original case preserved
        c.shutdown(socket.SHUT_WR)
        assert _recv_all(c) == "got jailbreak:Hello World"
        c.close()
        assert "toggle" not in seen           # ask must not fire a recording toggle
    finally:
        lis.stop()


def test_socket_toggle_still_works(tmp_path):
    toggled = []
    lis = SocketCommandListener(
        on_toggle=lambda a: toggled.append(a),
        agents=["jailbreak"],
        on_ask=lambda a, t: "unused",
    )
    lis._socket_path = str(tmp_path / "nova.sock")
    assert lis.start()
    try:
        c = _client(lis._socket_path)
        c.sendall(b"jailbreak")
        ack = c.recv(256).decode()
        c.close()
        assert "OK" in ack and "jailbreak" in ack
        time.sleep(0.1)
        assert toggled == ["jailbreak"]
    finally:
        lis.stop()


def test_socket_ask_bad_agent_errors(tmp_path):
    lis = SocketCommandListener(
        on_toggle=lambda a: None,
        agents=["jailbreak"],
        on_ask=lambda a, t: "should-not-run",
    )
    lis._socket_path = str(tmp_path / "nova.sock")
    assert lis.start()
    try:
        c = _client(lis._socket_path)
        c.sendall(b"ask nobody hi there")
        c.shutdown(socket.SHUT_WR)
        assert "ERROR" in _recv_all(c)
        c.close()
    finally:
        lis.stop()
