"""Strict, byte-oriented JSON decoding for trusted HND configuration and state."""
from __future__ import annotations

import json
from typing import Any


class StrictJSONError(ValueError):
    """Raised when JSON input violates the repository's strict decoding policy."""


def _reject_json_constant(_value: str) -> None:
    raise StrictJSONError("non-finite JSON constant is not allowed")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate object member names at every nesting level."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError("duplicate JSON object key")
        result[key] = value
    return result


def strict_json_loads(raw: bytes, *, label: str = "JSON input") -> Any:
    """Decode strict UTF-8 JSON bytes without duplicate keys or non-finite values.

    Integer tokens remain native Python integers. No Unicode normalization,
    whitespace rewriting, or canonicalization is performed here; callers that
    require canonical bytes must compare the original input with their existing
    canonical encoder after decoding.
    """
    if type(raw) is not bytes:
        raise StrictJSONError(f"{label}: input must be bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise StrictJSONError(f"{label}: UTF-8 BOM is not allowed")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StrictJSONError(f"{label}: invalid UTF-8") from exc

    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except StrictJSONError as exc:
        raise StrictJSONError(f"{label}: {exc}") from exc
    except RecursionError as exc:
        # Deeply nested input can exhaust the stdlib decoder's recursion budget.
        # Normalize it at the trust boundary so CLI/ABCI callers fail closed
        # instead of leaking an uncaught runtime exception.
        raise StrictJSONError(f"{label}: JSON nesting exceeds parser safety limit") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise StrictJSONError(f"{label}: invalid JSON") from exc
