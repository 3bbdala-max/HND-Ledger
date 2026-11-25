"""Mutual-TLS client for an independently operated monotonic anchor service.

The remote service MUST implement the linearizable, durable compare-and-advance
contract documented in docs/REMOTE_MONOTONIC_ANCHOR_PROTOCOL.md. This client
does not turn an ordinary database or a single-host service into an independent
trust domain; deployment must place the service in a separately administered
failure/security domain.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from hnd_v02.monotonic_anchor import (
    MonotonicAnchorError,
    MonotonicAnchorUnavailable,
    MonotonicRecord,
)

_MAX_RESPONSE_BYTES = 16_384
_MAX_SEQUENCE = (1 << 53) - 1


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("non-finite JSON number")


def _strict_json(raw: bytes) -> Any:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("invalid response size")
    return json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_pairs_no_duplicates,
        parse_constant=_reject_constant,
    )


def _record_from_json(value):
    if value is None:
        return None
    if type(value) is not dict or set(value) != {"sequence", "digest"}:
        raise ValueError("invalid anchor record shape")
    sequence, digest = value["sequence"], value["digest"]
    if type(sequence) is not int or not 0 <= sequence <= _MAX_SEQUENCE:
        raise ValueError("invalid anchor sequence")
    if type(digest) is not str or len(digest) != 64:
        raise ValueError("invalid anchor digest")
    if any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("invalid anchor digest")
    return MonotonicRecord(sequence, digest)


class RemoteMonotonicAnchor:
    """Strict HTTPS/mTLS adapter implementing MonotonicStateAnchor.

    An optional transport is provided for deterministic tests. Production
    callers should omit it and configure CA, client certificate and key files.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        ca_file: str,
        client_cert_file: str,
        client_key_file: str,
        timeout: float = 5.0,
        transport: Callable | None = None,
    ):
        if type(endpoint) is not str:
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-ENDPOINT")
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-HTTPS-REQUIRED")
        if type(timeout) not in (int, float) or timeout <= 0 or timeout > 60:
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-TIMEOUT")
        for path in (ca_file, client_cert_file, client_key_file):
            if type(path) is not str or not Path(path).is_file():
                raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-TLS-FILE")
        self.base_url = urlunsplit((
            "https", parsed.netloc, parsed.path.rstrip("/"), "", ""
        ))
        self.timeout = float(timeout)
        self.transport = transport
        self._ssl_context = None
        if self.transport is None:
            try:
                self._ssl_context = ssl.create_default_context(
                    purpose=ssl.Purpose.SERVER_AUTH, cafile=ca_file
                )
                self._ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                self._ssl_context.verify_mode = ssl.CERT_REQUIRED
                self._ssl_context.check_hostname = True
                self._ssl_context.load_cert_chain(
                    certfile=client_cert_file, keyfile=client_key_file
                )
            except (OSError, ssl.SSLError) as exc:
                raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-TLS-CONFIG") from exc

    def _post(self, route: str, payload: Mapping) -> Any:
        body = json.dumps(
            payload, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"), sort_keys=True,
        ).encode("ascii")
        url = self.base_url + route
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        }
        try:
            if self.transport is not None:
                status, response_headers, response_body = self.transport(
                    url, body, headers, self.timeout
                )
            else:
                request = urllib.request.Request(
                    url, data=body, headers=headers, method="POST"
                )
                opener = urllib.request.build_opener(
                    urllib.request.HTTPSHandler(context=self._ssl_context),
                    _NoRedirect(),
                )
                with opener.open(request, timeout=self.timeout) as response:
                    status = response.status
                    response_headers = response.headers
                    response_body = response.read(_MAX_RESPONSE_BYTES + 1)
            if status != 200:
                raise ValueError("unexpected anchor HTTP status")
            content_type = response_headers.get("Content-Type", "")
            if content_type.split(";", 1)[0].strip().lower() != "application/json":
                raise ValueError("unexpected anchor content type")
            return _strict_json(response_body)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError,
                UnicodeError, json.JSONDecodeError) as exc:
            raise MonotonicAnchorUnavailable(
                "HND-REMOTE-ANCHOR-E-REQUEST"
            ) from exc

    def read_state(self, namespace: str) -> MonotonicRecord | None:
        if type(namespace) is not str or namespace not in {
            "trust-manifest", "vsp-profile", "activation-witness"
        }:
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-NAMESPACE")
        try:
            response = self._post("/v1/state/read", {"namespace": namespace})
            if type(response) is not dict or set(response) != {"record"}:
                raise ValueError("invalid read response")
            return _record_from_json(response["record"])
        except MonotonicAnchorUnavailable:
            raise
        except Exception as exc:
            raise MonotonicAnchorUnavailable(
                "HND-REMOTE-ANCHOR-E-READ-RESPONSE"
            ) from exc

    def compare_and_advance(
        self, namespace: str, expected_current: MonotonicRecord | None,
        new_record: MonotonicRecord,
    ) -> bool:
        if type(namespace) is not str or namespace not in {
            "trust-manifest", "vsp-profile", "activation-witness"
        }:
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-NAMESPACE")
        if expected_current is not None and type(expected_current) is not MonotonicRecord:
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-EXPECTED")
        if type(new_record) is not MonotonicRecord:
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-NEW-RECORD")
        # Validate record values before putting them on the wire.
        try:
            for record in (expected_current, new_record):
                if record is not None:
                    _record_from_json({
                        "sequence": record.sequence, "digest": record.digest
                    })
        except (TypeError, ValueError) as exc:
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-RECORD") from exc
        bootstrap = {"trust-manifest": 0, "vsp-profile": 1, "activation-witness": 0}[namespace]
        expected_sequence = (
            bootstrap if expected_current is None
            else expected_current.sequence + 1
        )
        if expected_sequence > _MAX_SEQUENCE or new_record.sequence != expected_sequence:
            raise MonotonicAnchorError("HND-REMOTE-ANCHOR-E-SEQUENCE")
        payload = {
            "namespace": namespace,
            "expected_current": None if expected_current is None else {
                "sequence": expected_current.sequence,
                "digest": expected_current.digest,
            },
            "new_record": {
                "sequence": new_record.sequence, "digest": new_record.digest,
            },
        }
        try:
            response = self._post("/v1/state/compare-and-advance", payload)
            if type(response) is not dict or set(response) != {"advanced"}:
                raise ValueError("invalid CAS response")
            if type(response["advanced"]) is not bool:
                raise ValueError("invalid CAS result")
            return response["advanced"]
        except MonotonicAnchorUnavailable:
            raise
        except Exception as exc:
            raise MonotonicAnchorUnavailable(
                "HND-REMOTE-ANCHOR-E-CAS-RESPONSE"
            ) from exc
