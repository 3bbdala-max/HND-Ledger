"""Strict HTTPS/mTLS client for the Station 2 witness acknowledgement API.

The supplied SSLContext must contain the client certificate/key and trust roots
for the witness server. Server certificate validation and hostname checking are
mandatory. This client transports receipts; the etcd finalizer performs the
cryptographic identity, epoch, commitment, and signature verification.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from typing import Any

_MAX_RESPONSE_BYTES = 8192
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ROUTE = "/v1/witness/acknowledge"


class ActivationWitnessClientError(RuntimeError):
    """The witness endpoint could not safely acknowledge the activation."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class HTTPSActivationWitnessClient:
    """mTLS client for one pinned HTTPS witness service origin."""

    def __init__(
        self,
        endpoint: str,
        *,
        ssl_context: ssl.SSLContext,
        timeout: float = 5.0,
    ):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.netloc
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ActivationWitnessClientError("HND-WITNESS-CLIENT-E-ENDPOINT")
        if not isinstance(ssl_context, ssl.SSLContext):
            raise ActivationWitnessClientError("HND-WITNESS-CLIENT-E-TLS-CONTEXT")
        if ssl_context.verify_mode != ssl.CERT_REQUIRED or not ssl_context.check_hostname:
            raise ActivationWitnessClientError("HND-WITNESS-CLIENT-E-SERVER-AUTH")
        if ssl_context.minimum_version < ssl.TLSVersion.TLSv1_2:
            raise ActivationWitnessClientError("HND-WITNESS-CLIENT-E-TLS-VERSION")
        if type(timeout) not in (int, float) or timeout <= 0 or timeout > 60:
            raise ActivationWitnessClientError("HND-WITNESS-CLIENT-E-TIMEOUT")
        self.endpoint = endpoint.rstrip("/")
        self.ssl_context = ssl_context
        self.timeout = float(timeout)

    def acknowledge(self, activation_id: str, activation_digest: str) -> dict[str, Any]:
        if type(activation_id) is not str or not _ID.fullmatch(activation_id):
            raise ActivationWitnessClientError("HND-WITNESS-CLIENT-E-ACTIVATION-ID")
        if type(activation_digest) is not str or not _HEX64.fullmatch(activation_digest):
            raise ActivationWitnessClientError("HND-WITNESS-CLIENT-E-DIGEST")
        body = json.dumps(
            {"activation_id": activation_id, "activation_digest": activation_digest},
            ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"),
        ).encode("ascii")
        request = urllib.request.Request(
            self.endpoint + _ROUTE,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        opener = urllib.request.build_opener(
            _NoRedirectHandler,
            urllib.request.HTTPSHandler(context=self.ssl_context),
        )
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise ValueError("response too large")
            payload = json.loads(
                raw.decode("utf-8", errors="strict"),
                object_pairs_hook=_pairs_no_duplicates,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("non-finite JSON number")
                ),
            )
            if (type(payload) is not dict or set(payload) != {"receipt"}
                    or type(payload["receipt"]) is not dict):
                raise ValueError("response shape")
            return payload["receipt"]
        except urllib.error.HTTPError as exc:
            raise ActivationWitnessClientError(
                "HND-WITNESS-CLIENT-E-HTTP-" + str(exc.code)
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                UnicodeError, json.JSONDecodeError) as exc:
            raise ActivationWitnessClientError("HND-WITNESS-CLIENT-E-REQUEST") from exc
