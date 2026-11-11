"""mTLS HTTPS server for the remote activation-intent v2 protocol.

The caller supplies a server SSLContext with its certificate/key and trusted
client CA loaded. This server additionally pins authorized client certificate
SHA-256 fingerprints. It is a single-host service when backed by SQLite; it
does not claim multi-replica linearizability or protection from host rollback.
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

from hnd_v02.remote_activation_intent import RemoteActivationProtocolError
from hnd_v02.sqlite_activation_intent_store import SQLiteActivationIntentStore

_MAX_REQUEST_BYTES = 16_384
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ROUTES = {
    "/v2/activation/prepare",
    "/v2/activation/read",
    "/v2/activation/finalize",
}


class ActivationIntentHTTPError(ValueError):
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


def dispatch_activation_request(
    store: SQLiteActivationIntentStore, route: str, payload: Mapping[str, Any]
) -> dict:
    """Pure protocol dispatch; HTTP and TLS concerns stay outside this function."""
    if route not in _ROUTES or type(payload) is not dict:
        raise ActivationIntentHTTPError(404, "HND-ACT-SERVER-E-ROUTE")
    try:
        if route == "/v2/activation/prepare":
            return store.prepare(payload)
        if route == "/v2/activation/read":
            if set(payload) != {"activation_id"}:
                raise ActivationIntentHTTPError(400, "HND-ACT-SERVER-E-READ-SHAPE")
            return {"intent": store.read_intent(payload["activation_id"])}
        if set(payload) != {"activation_id", "profile_digest", "operator_ack_digest"}:
            raise ActivationIntentHTTPError(400, "HND-ACT-SERVER-E-FINALIZE-SHAPE")
        return store.finalize(
            payload["activation_id"], payload["profile_digest"],
            payload["operator_ack_digest"],
        )
    except RemoteActivationProtocolError as exc:
        code = str(exc)
        if code.endswith("-NOT-FOUND"):
            raise ActivationIntentHTTPError(404, "HND-ACT-SERVER-E-NOT-FOUND") from exc
        if any(code.endswith(suffix) for suffix in (
            "-ID-CONFLICT", "-DIGEST-MISMATCH", "-SEQUENCE",
            "-ACTIVE-INTENT", "-MULTIPLE-ACTIVE-INTENTS", "-GUARD-MISMATCH", "-ORPHAN-GUARD",
        )):
            raise ActivationIntentHTTPError(409, "HND-ACT-SERVER-E-CONFLICT") from exc
        raise ActivationIntentHTTPError(400, "HND-ACT-SERVER-E-INVALID") from exc


def create_activation_intent_server(
    store: SQLiteActivationIntentStore,
    *,
    ssl_context: ssl.SSLContext,
    authorized_client_cert_sha256: set[str] | frozenset[str],
    address: tuple[str, int] = ("127.0.0.1", 9443),
) -> ThreadingHTTPServer:
    """Create an mTLS server pinned to an explicit client-certificate allowlist.

    Configure ssl_context with load_cert_chain(server_cert, server_key),
    load_verify_locations(client_ca), CERT_REQUIRED and TLS 1.2+ before calling.
    """
    if not isinstance(store, SQLiteActivationIntentStore):
        raise ValueError("a durable SQLiteActivationIntentStore is required")
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
        server_version = "HND-Activation/2"
        sys_version = ""

        def log_message(self, _format, *_args):
            # Do not log request bodies, identifiers, or certificate material.
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
                self._send(403, {"error": "HND-ACT-SERVER-E-CLIENT-AUTH"})
                return
            if self.path not in _ROUTES:
                self._send(404, {"error": "HND-ACT-SERVER-E-ROUTE"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                self._send(415, {"error": "HND-ACT-SERVER-E-CONTENT-TYPE"})
                return
            length = self.headers.get("Content-Length")
            if length is None or not length.isascii() or not length.isdigit():
                self._send(400, {"error": "HND-ACT-SERVER-E-LENGTH"})
                return
            size = int(length)
            if size < 1 or size > _MAX_REQUEST_BYTES:
                self._send(413, {"error": "HND-ACT-SERVER-E-SIZE"})
                return
            try:
                payload = _strict_loads(self.rfile.read(size))
                if type(payload) is not dict:
                    raise ValueError("JSON object required")
                result = dispatch_activation_request(store, self.path, payload)
                self._send(200, result)
            except ActivationIntentHTTPError as exc:
                self._send(exc.status, {"error": exc.code})
            except (ValueError, UnicodeError, json.JSONDecodeError):
                self._send(400, {"error": "HND-ACT-SERVER-E-JSON"})
            except Exception:
                # Fail closed without exposing storage details to the network.
                self._send(503, {"error": "HND-ACT-SERVER-E-UNAVAILABLE"})

    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = True
    server.allow_reuse_address = False
    server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    return server
