"""mTLS HTTPS reference server for the remote monotonic-anchor v1 protocol.

SQLite is a single-host reference backend only. A production anti-rollback
anchor must be independently administered, durable and linearizable.
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from hnd_v02.monotonic_anchor import (
    MonotonicAnchorConflict, MonotonicAnchorError, MonotonicRecord,
    MonotonicStateAnchor,
)
from hnd_v02.sqlite_monotonic_anchor import SQLiteMonotonicAnchor

_MAX_REQUEST_BYTES = 16_384
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ROUTES = {"/v1/state/read", "/v1/state/compare-and-advance"}
_NAMESPACES = {"trust-manifest", "vsp-profile"}


class MonotonicAnchorHTTPError(ValueError):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("non-finite JSON number")


def _strict_loads(raw: bytes) -> Any:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_REQUEST_BYTES:
        raise ValueError("invalid request size")
    return json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_pairs_no_duplicates,
        parse_constant=_reject_constant,
    )


def _record(value, *, nullable: bool) -> MonotonicRecord | None:
    if value is None and nullable:
        return None
    if type(value) is not dict or set(value) != {"sequence", "digest"}:
        raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-RECORD")
    sequence, digest = value["sequence"], value["digest"]
    if (type(sequence) is not int or not 0 <= sequence <= (1 << 53) - 1
            or type(digest) is not str or not _HEX64.fullmatch(digest)):
        raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-RECORD")
    return MonotonicRecord(sequence, digest)


def dispatch_monotonic_anchor_request(
    anchor: MonotonicStateAnchor, route: str, payload: Mapping[str, Any]
) -> dict:
    """Dispatch the exact v1 read and compare-and-advance wire contract."""
    if route not in _ROUTES:
        raise MonotonicAnchorHTTPError(404, "HND-ANCHOR-SERVER-E-ROUTE")
    if type(payload) is not dict:
        raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-SHAPE")
    if route == "/v1/state/read":
        if set(payload) != {"namespace"}:
            raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-READ-SHAPE")
        namespace = payload["namespace"]
        if type(namespace) is not str or namespace not in _NAMESPACES:
            raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-NAMESPACE")
        current = anchor.read_state(namespace)
        return {"record": None if current is None else {
            "sequence": current.sequence, "digest": current.digest,
        }}

    if set(payload) != {"namespace", "expected_current", "new_record"}:
        raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-CAS-SHAPE")
    namespace = payload["namespace"]
    if type(namespace) is not str or namespace not in _NAMESPACES:
        raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-NAMESPACE")
    expected = _record(payload["expected_current"], nullable=True)
    proposed = _record(payload["new_record"], nullable=False)
    try:
        advanced = anchor.compare_and_advance(namespace, expected, proposed)
    except MonotonicAnchorConflict as exc:
        raise MonotonicAnchorHTTPError(409, "HND-ANCHOR-SERVER-E-CONFLICT") from exc
    except MonotonicAnchorError as exc:
        raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-INVALID") from exc
    return {"advanced": advanced}


def create_monotonic_anchor_server(
    anchor: MonotonicStateAnchor,
    *,
    ssl_context: ssl.SSLContext,
    authorized_client_cert_sha256: set[str] | frozenset[str],
    address: tuple[str, int] = ("127.0.0.1", 9444),
) -> ThreadingHTTPServer:
    """Create a pinned mTLS server; caller provisions certs, CA and TLS context."""
    if not callable(getattr(anchor, "read_state", None)) or not callable(
        getattr(anchor, "compare_and_advance", None)
    ):
        raise ValueError("a MonotonicStateAnchor implementation is required")
    if not isinstance(ssl_context, ssl.SSLContext):
        raise ValueError("a server SSLContext is required")
    if ssl_context.protocol not in (ssl.PROTOCOL_TLS_SERVER, ssl.PROTOCOL_TLS):
        raise ValueError("server TLS context required")
    if ssl_context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError("client certificate authentication is mandatory")
    if ssl_context.minimum_version < ssl.TLSVersion.TLSv1_2:
        raise ValueError("TLS 1.2 minimum is mandatory")
    pins = frozenset(authorized_client_cert_sha256)
    if not pins or any(type(pin) is not str or not _HEX64.fullmatch(pin) for pin in pins):
        raise ValueError("explicit lowercase SHA-256 client certificate pins required")

    class Handler(BaseHTTPRequestHandler):
        server_version = "HND-Monotonic-Anchor/1"
        sys_version = ""

        def log_message(self, _format, *_args):
            return

        def _send(self, status: int, value: dict):
            body = json.dumps(
                value, ensure_ascii=True, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ).encode("ascii")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            peer_cert = self.connection.getpeercert(binary_form=True)
            if not peer_cert or hashlib.sha256(peer_cert).hexdigest() not in pins:
                self._send(403, {"error": "HND-ANCHOR-SERVER-E-CLIENT-AUTH"})
                return
            if self.path not in _ROUTES:
                self._send(404, {"error": "HND-ANCHOR-SERVER-E-ROUTE"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                self._send(415, {"error": "HND-ANCHOR-SERVER-E-CONTENT-TYPE"})
                return
            length = self.headers.get("Content-Length")
            if length is None or not length.isascii() or not length.isdigit():
                self._send(400, {"error": "HND-ANCHOR-SERVER-E-LENGTH"})
                return
            size = int(length)
            if size < 1 or size > _MAX_REQUEST_BYTES:
                self._send(413, {"error": "HND-ANCHOR-SERVER-E-SIZE"})
                return
            try:
                payload = _strict_loads(self.rfile.read(size))
                if type(payload) is not dict:
                    raise ValueError("JSON object required")
                result = dispatch_monotonic_anchor_request(anchor, self.path, payload)
                self._send(200, result)
            except MonotonicAnchorHTTPError as exc:
                self._send(exc.status, {"error": exc.code})
            except (ValueError, UnicodeError, json.JSONDecodeError):
                self._send(400, {"error": "HND-ANCHOR-SERVER-E-JSON"})
            except Exception:
                self._send(503, {"error": "HND-ANCHOR-SERVER-E-UNAVAILABLE"})

    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = True
    server.allow_reuse_address = False
    server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    return server
