"""mTLS HTTPS reference server for the remote monotonic-anchor v1 protocol.

SQLite is a single-host reference backend only. A production anti-rollback
anchor must be independently administered, durable and linearizable.
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import threading
from dataclasses import dataclass
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
_NAMESPACES = {"trust-manifest", "vsp-profile", "activation-witness"}
_OPERATIONS = {"read", "compare-and-advance"}
_PRINCIPAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$", re.ASCII)


@dataclass(frozen=True)
class AnchorClientPolicy:
    """Immutable authorization policy for one mTLS certificate identity."""

    principal_id: str
    role: str
    namespaces: frozenset[str]
    operations: frozenset[str]

    def __post_init__(self):
        if type(self.principal_id) is not str or not _PRINCIPAL.fullmatch(self.principal_id):
            raise ValueError("valid principal_id required")
        if type(self.role) is not str:
            raise ValueError("valid anchor client role required")
        if type(self.namespaces) is not frozenset or not self.namespaces <= _NAMESPACES:
            raise ValueError("valid immutable namespace set required")
        if type(self.operations) is not frozenset or not self.operations <= _OPERATIONS:
            raise ValueError("valid immutable operation set required")
        expected = {
            "witness": (frozenset({"activation-witness"}), _OPERATIONS),
            "trust-manifest-authority": (frozenset({"trust-manifest"}), _OPERATIONS),
            "vsp-profile-authority": (frozenset({"vsp-profile"}), _OPERATIONS),
            "finalizer": (_NAMESPACES, frozenset({"read"})),
            # No recovery or operator mutation endpoint exists in API v1.
            "recovery": (frozenset(), frozenset()),
            "operator": (frozenset(), frozenset()),
        }
        if self.role not in expected:
            raise ValueError("unknown anchor client role")
        allowed_namespaces, allowed_operations = expected[self.role]
        if (not self.namespaces or not self.operations
                if self.role in {"witness", "trust-manifest-authority",
                                 "vsp-profile-authority", "finalizer"}
                else bool(self.namespaces or self.operations)):
            raise ValueError("role requires an exact non-empty or empty policy")
        if not self.namespaces <= allowed_namespaces or not self.operations <= allowed_operations:
            raise ValueError("policy exceeds role authority")
        if self.role in {"witness", "trust-manifest-authority", "vsp-profile-authority"}:
            if self.namespaces != allowed_namespaces or self.operations != _OPERATIONS:
                raise ValueError("namespace writer role requires its exact namespace and operations")
        if self.role == "finalizer" and self.operations != frozenset({"read"}):
            raise ValueError("finalizer is read-only")


class AnchorClientRegistry:
    """Thread-safe live certificate registry; removal revokes, replacement rotates."""

    def __init__(self, clients: Mapping[str, AnchorClientPolicy]):
        if not isinstance(clients, Mapping) or not clients:
            raise ValueError("non-empty certificate authorization registry required")
        self._lock = threading.RLock()
        self._clients = {}
        for fingerprint, policy in clients.items():
            self._validate_fingerprint(fingerprint)
            if type(policy) is not AnchorClientPolicy:
                raise ValueError("AnchorClientPolicy values required")
            self._clients[fingerprint] = policy

    @staticmethod
    def _validate_fingerprint(fingerprint):
        if type(fingerprint) is not str or not _HEX64.fullmatch(fingerprint):
            raise ValueError("lowercase SHA-256 certificate fingerprint required")

    def authorize(self, fingerprint: str, operation: str, namespace: str) -> AnchorClientPolicy:
        with self._lock:
            policy = self._clients.get(fingerprint)
        if (policy is None or operation not in policy.operations
                or namespace not in policy.namespaces):
            raise MonotonicAnchorHTTPError(403, "HND-ANCHOR-SERVER-E-AUTHZ")
        return policy

    def revoke(self, fingerprint: str) -> None:
        self._validate_fingerprint(fingerprint)
        with self._lock:
            self._clients.pop(fingerprint, None)

    def register(self, fingerprint: str, policy: AnchorClientPolicy) -> None:
        self._validate_fingerprint(fingerprint)
        if type(policy) is not AnchorClientPolicy:
            raise ValueError("AnchorClientPolicy required")
        with self._lock:
            if fingerprint in self._clients:
                raise ValueError("certificate fingerprint already registered")
            self._clients[fingerprint] = policy

    def rotate(self, old_fingerprint: str, new_fingerprint: str,
               policy: AnchorClientPolicy) -> None:
        self._validate_fingerprint(old_fingerprint)
        self._validate_fingerprint(new_fingerprint)
        if old_fingerprint == new_fingerprint or type(policy) is not AnchorClientPolicy:
            raise ValueError("distinct fingerprints and policy required")
        with self._lock:
            old_policy = self._clients.get(old_fingerprint)
            if old_policy is None or new_fingerprint in self._clients:
                raise ValueError("rotation source missing or destination already registered")
            if (policy.principal_id != old_policy.principal_id
                    or policy.role != old_policy.role
                    or not policy.namespaces <= old_policy.namespaces
                    or not policy.operations <= old_policy.operations):
                raise ValueError("certificate rotation cannot broaden or change principal authority")
            self._clients[new_fingerprint] = policy
            del self._clients[old_fingerprint]


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
    anchor: MonotonicStateAnchor, route: str, payload: Mapping[str, Any],
    *, client_policy: AnchorClientPolicy | None = None,
) -> dict:
    """Dispatch v1 only after enforcing the supplied authenticated client policy."""
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
        if client_policy is not None and ("read" not in client_policy.operations
                or namespace not in client_policy.namespaces):
            raise MonotonicAnchorHTTPError(403, "HND-ANCHOR-SERVER-E-AUTHZ")
        current = anchor.read_state(namespace)
        return {"record": None if current is None else {
            "sequence": current.sequence, "digest": current.digest,
        }}

    if set(payload) != {"namespace", "expected_current", "new_record"}:
        raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-CAS-SHAPE")
    namespace = payload["namespace"]
    if type(namespace) is not str or namespace not in _NAMESPACES:
        raise MonotonicAnchorHTTPError(400, "HND-ANCHOR-SERVER-E-NAMESPACE")
    if client_policy is not None and ("compare-and-advance" not in client_policy.operations
            or namespace not in client_policy.namespaces):
        raise MonotonicAnchorHTTPError(403, "HND-ANCHOR-SERVER-E-AUTHZ")
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
    client_registry: AnchorClientRegistry,
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
    if type(client_registry) is not AnchorClientRegistry:
        raise ValueError("explicit role-based AnchorClientRegistry required")

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
            if not peer_cert:
                self._send(403, {"error": "HND-ANCHOR-SERVER-E-CLIENT-AUTH"})
                return
            fingerprint = hashlib.sha256(peer_cert).hexdigest()
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
                namespace = payload.get("namespace")
                if type(namespace) is not str or namespace not in _NAMESPACES:
                    raise MonotonicAnchorHTTPError(
                        400, "HND-ANCHOR-SERVER-E-NAMESPACE"
                    )
                operation = "read" if self.path == "/v1/state/read" else "compare-and-advance"
                try:
                    policy = client_registry.authorize(fingerprint, operation, namespace)
                except MonotonicAnchorHTTPError as exc:
                    self._send(exc.status, {"error": exc.code})
                    return
                result = dispatch_monotonic_anchor_request(
                    anchor, self.path, payload, client_policy=policy
                )
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
