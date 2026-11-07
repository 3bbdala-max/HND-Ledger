"""Bounded Unix-domain JSONL IPC server for the Go ABCI transport adapter.

This module implements framing and envelope validation only. The application
dispatcher must explicitly implement each ABCI method; unknown methods fail
closed. It never opens a TCP listener.
"""
from __future__ import annotations

import json
import os
import re
import socketserver
import stat
from pathlib import Path
from typing import Any, Callable

PROTOCOL_VERSION = "hnd-ipc/1"
MAX_FRAME_BYTES = 1 << 20
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_METHOD_RE = re.compile(r"^[A-Z][A-Za-z0-9]{0,63}$")


class IPCError(ValueError):
    """A malformed or unsupported IPC request."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IPCError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _loads_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IPCError("request is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise IPCError("request envelope must be a JSON object")
    return value


def decode_request(raw: bytes) -> tuple[str, str, dict[str, Any]]:
    """Validate one complete request frame and return id, method, payload."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_FRAME_BYTES:
        raise IPCError("request frame is empty or exceeds the size limit")
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise IPCError("request must contain exactly one newline-terminated frame")
    envelope = _loads_object(raw[:-1])
    if set(envelope) != {"protocol", "id", "method", "payload"}:
        raise IPCError("request envelope fields do not match protocol")
    if envelope["protocol"] != PROTOCOL_VERSION:
        raise IPCError("unsupported IPC protocol version")
    request_id = envelope["id"]
    method = envelope["method"]
    payload = envelope["payload"]
    if not isinstance(request_id, str) or not _ID_RE.fullmatch(request_id):
        raise IPCError("invalid request id")
    if not isinstance(method, str) or not _METHOD_RE.fullmatch(method):
        raise IPCError("invalid method name")
    if not isinstance(payload, dict):
        raise IPCError("request payload must be a JSON object")
    return request_id, method, payload


def encode_response(request_id: str, *, result: Any = None,
                    error: dict[str, Any] | None = None) -> bytes:
    response = {
        "protocol": PROTOCOL_VERSION,
        "id": request_id,
        "ok": error is None,
    }
    if error is None:
        response["result"] = {} if result is None else result
    else:
        response["error"] = error
    try:
        raw = json.dumps(response, separators=(",", ":"), sort_keys=True,
                         ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise IPCError("dispatcher returned a non-JSON result") from exc
    if len(raw) > MAX_FRAME_BYTES:
        raise IPCError("response exceeds the IPC frame limit")
    return raw


class _UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_FRAME_BYTES + 1)
        request_id = "invalid"
        try:
            request_id, method, payload = decode_request(raw)
            dispatcher: Callable[[str, dict[str, Any]], Any] = self.server.dispatcher  # type: ignore[attr-defined]
            result = dispatcher(method, payload)
            response = encode_response(request_id, result=result)
        except IPCError as exc:
            response = encode_response(request_id, error={
                "code": "INVALID_REQUEST", "message": str(exc), "retryable": False,
            })
        except NotImplementedError as exc:
            response = encode_response(request_id, error={
                "code": "UNSUPPORTED_METHOD", "message": str(exc), "retryable": False,
            })
        except Exception:
            # Do not leak stack traces, paths, keys, or internal state over IPC.
            response = encode_response(request_id, error={
                "code": "INTERNAL_ERROR", "message": "application request failed",
                "retryable": True,
            })
        self.wfile.write(response)
        self.wfile.flush()


class IPCServer:
    """Context-managed, local-only IPC server with restrictive socket mode."""

    def __init__(self, socket_path: str | Path,
                 dispatcher: Callable[[str, dict[str, Any]], Any]):
        self.socket_path = Path(socket_path)
        self.dispatcher = dispatcher
        self._server: _UnixServer | None = None

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("IPC server is already running")
        if self.socket_path.exists():
            info = self.socket_path.lstat()
            if not stat.S_ISSOCK(info.st_mode):
                raise RuntimeError("refusing to replace a non-socket IPC path")
            self.socket_path.unlink()
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        server = _UnixServer(str(self.socket_path), _Handler)
        server.dispatcher = self.dispatcher  # type: ignore[attr-defined]
        os.chmod(self.socket_path, 0o600)
        self._server = server

    def serve_forever(self) -> None:
        if self._server is None:
            self.start()
        assert self._server is not None
        self._server.serve_forever()

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        try:
            if self.socket_path.exists() and stat.S_ISSOCK(self.socket_path.lstat().st_mode):
                self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> "IPCServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
