"""HTTPS/mTLS endpoint for the Station 2 activation witness backend.

Production suitability is determined by the backend admission gate and by
independently verified deployment evidence, not by this HTTP service alone.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from hnd_v02.activation_witness_interface import (
    ActivationWitnessStore, ActivationWitnessStoreError,
)
from hnd_v02.witness_production_attestation import require_production_witness_backend

_MAX_REQUEST_BYTES = 4096
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ROUTE = "/v1/witness/acknowledge"


class ActivationWitnessHTTPError(ValueError):
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


def _strict_loads(raw: bytes) -> Any:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_REQUEST_BYTES:
        raise ValueError("invalid request size")
    return json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_pairs_no_duplicates,
        parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
    )


def dispatch_witness_request(
    store: ActivationWitnessStore, route: str, payload: Any
) -> dict:
    if route != _ROUTE:
        raise ActivationWitnessHTTPError(404, "HND-WITNESS-HTTP-E-ROUTE")
    if type(payload) is not dict or set(payload) != {"activation_id", "activation_digest"}:
        raise ActivationWitnessHTTPError(400, "HND-WITNESS-HTTP-E-SHAPE")
    activation_id, digest = payload["activation_id"], payload["activation_digest"]
    if type(activation_id) is not str or not _ID.fullmatch(activation_id):
        raise ActivationWitnessHTTPError(400, "HND-WITNESS-HTTP-E-ACTIVATION-ID")
    if type(digest) is not str or not _HEX64.fullmatch(digest):
        raise ActivationWitnessHTTPError(400, "HND-WITNESS-HTTP-E-DIGEST")
    try:
        return {"receipt": store.acknowledge(activation_id, digest)}
    except ActivationWitnessStoreError as exc:
        code = str(exc)
        status = 409 if any(
            marker in code for marker in (
                "ID-CONFLICT", "PENDING-CONFLICT",
                "TERMINAL-EVIDENCE-MISSING",
            )
        ) else 503
        raise ActivationWitnessHTTPError(status, code) from exc


def create_activation_witness_server(
    store: ActivationWitnessStore,
    *,
    ssl_context: ssl.SSLContext,
    authorized_client_cert_sha256: set[str] | frozenset[str],
    address: tuple[str, int] = ("127.0.0.1", 9445),
    require_production_backend: bool = True,
    production_attestation: dict | None = None,
    trusted_attestor_public_key: bytes | None = None,
) -> ThreadingHTTPServer:
    if not callable(getattr(store, "acknowledge", None)):
        raise ValueError("HND-WITNESS-SERVICE-E-STORE-INTERFACE")
    if type(require_production_backend) is not bool:
        raise ValueError("HND-WITNESS-SERVICE-E-MODE")
    if not require_production_backend:
        try:
            bind_host, bind_port = address
            loopback = ipaddress.ip_address(bind_host).is_loopback
        except (TypeError, ValueError):
            loopback = False
            bind_port = None
        if (not loopback or type(bind_port) is not int
                or not 0 <= bind_port <= 65535):
            raise ValueError("HND-WITNESS-SERVICE-E-DEVELOPMENT-BIND")
    if require_production_backend:
        require_production_witness_backend(
            store, attestation=production_attestation,
            trusted_attestor_public_key=trusted_attestor_public_key,
        )
    if not isinstance(ssl_context, ssl.SSLContext):
        raise ValueError("server SSLContext required")
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
        server_version = "HND-Activation-Witness/1"
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
                self._send(403, {"error": "HND-WITNESS-HTTP-E-CLIENT-AUTH"})
                return
            if self.path != _ROUTE:
                self._send(404, {"error": "HND-WITNESS-HTTP-E-ROUTE"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                self._send(415, {"error": "HND-WITNESS-HTTP-E-CONTENT-TYPE"})
                return
            length = self.headers.get("Content-Length")
            if length is None or not length.isascii() or not length.isdigit():
                self._send(400, {"error": "HND-WITNESS-HTTP-E-LENGTH"})
                return
            size = int(length)
            if size < 1 or size > _MAX_REQUEST_BYTES:
                self._send(413, {"error": "HND-WITNESS-HTTP-E-SIZE"})
                return
            try:
                payload = _strict_loads(self.rfile.read(size))
                self._send(200, dispatch_witness_request(store, self.path, payload))
            except ActivationWitnessHTTPError as exc:
                self._send(exc.status, {"error": str(exc)})
            except (ValueError, UnicodeError, json.JSONDecodeError):
                self._send(400, {"error": "HND-WITNESS-HTTP-E-JSON"})
            except Exception:
                self._send(503, {"error": "HND-WITNESS-HTTP-E-UNAVAILABLE"})

    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = True
    server.allow_reuse_address = False
    server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    return server
