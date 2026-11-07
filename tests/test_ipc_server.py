import json
import socket
import threading

import pytest

from hnd_ledger.ipc_server import (
    IPCError, IPCServer, MAX_FRAME_BYTES, PROTOCOL_VERSION, decode_request,
)


def frame(payload=None, **overrides):
    value = {
        "protocol": PROTOCOL_VERSION,
        "id": "go-1",
        "method": "Info",
        "payload": {} if payload is None else payload,
    }
    value.update(overrides)
    return json.dumps(value, separators=(",", ":")).encode() + b"\n"


def test_decode_valid_request():
    assert decode_request(frame({"height": 2})) == ("go-1", "Info", {"height": 2})


@pytest.mark.parametrize("raw", [
    b"",
    b'{"protocol":"hnd-ipc/1","id":"x","method":"Info","payload":{}}',
    frame() + frame(),
    frame(protocol="hnd-ipc/2"),
    frame(extra=True),
    frame(id=""),
    frame(method="info"),
    frame(payload=[]),
    b'{"protocol":"hnd-ipc/1","id":"x","id":"y","method":"Info","payload":{}}\n',
])
def test_rejects_malformed_or_ambiguous_frames(raw):
    with pytest.raises(IPCError):
        decode_request(raw)


def test_rejects_oversized_frame():
    with pytest.raises(IPCError):
        decode_request(b"x" * (MAX_FRAME_BYTES + 1))


def test_server_dispatches_over_unix_socket_and_returns_correlated_response(tmp_path):
    path = tmp_path / "hnd.sock"
    server = IPCServer(path, lambda method, payload: {"method": method, "echo": payload})
    server.start()
    thread = threading.Thread(target=server._server.serve_forever, daemon=True)
    thread.start()
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(path))
        client.sendall(frame({"n": 7}))
        client.shutdown(socket.SHUT_WR)
        received = b""
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            received += chunk
        client.close()
        reply = json.loads(received)
        assert reply["protocol"] == PROTOCOL_VERSION
        assert reply["id"] == "go-1"
        assert reply["ok"] is True
        assert reply["result"] == {"method": "Info", "echo": {"n": 7}}
    finally:
        server.close()
        thread.join(timeout=2)


def test_unknown_method_fails_closed_over_socket(tmp_path):
    path = tmp_path / "hnd.sock"
    server = IPCServer(path, lambda method, payload: (_ for _ in ()).throw(NotImplementedError(method)))
    server.start()
    thread = threading.Thread(target=server._server.serve_forever, daemon=True)
    thread.start()
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(path))
        client.sendall(frame())
        client.shutdown(socket.SHUT_WR)
        response = json.loads(client.makefile("rb").readline())
        assert response["ok"] is False
        assert response["error"]["code"] == "UNSUPPORTED_METHOD"
        client.close()
    finally:
        server.close()
        thread.join(timeout=2)
