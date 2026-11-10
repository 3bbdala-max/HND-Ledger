"""Strict schema-driven CometBFT v0.40.0 TOML profile boundary."""
from __future__ import annotations
import copy, hashlib, json, tomllib
from dataclasses import dataclass
from typing import Any, Mapping

COMETBFT_V040_SOURCE_COMMIT = "0880b4d378f347ab16e54ec677ff50d803f37d62"
PROFILE_DOMAIN = b"HND-COMETBFT-V040-PROFILE-v1\x00"
MAX_CONFIG_BYTES = 1_048_576
MAX_INTEGER = (1 << 53) - 1

class CometBFTProfileError(ValueError):
    """Fail-closed error at the CometBFT profile trust boundary."""

@dataclass(frozen=True)
class FieldRule:
    value_type: type | tuple[type, ...]
    scope: str
    default: Any = None
    has_default: bool = False

@dataclass(frozen=True)
class ProfileSchema:
    source_commit: str
    fields: Mapping[str, FieldRule]
    complete: bool

def _validate_tree(value: Any, path: str) -> None:
    if isinstance(value, str):
        try: value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc: raise CometBFTProfileError(f"{path}: invalid Unicode scalar") from exc
    elif isinstance(value, list):
        for i, item in enumerate(value): _validate_tree(item, f"{path}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str): raise CometBFTProfileError(f"{path}: non-string key")
            _validate_tree(key, path); _validate_tree(item, f"{path}.{key}")
    elif value is None or isinstance(value, (bool, int)):
        if isinstance(value, int) and not isinstance(value, bool) and not -MAX_INTEGER <= value <= MAX_INTEGER:
            raise CometBFTProfileError(f"{path}: integer exceeds safe profile bound")
    else:
        raise CometBFTProfileError(f"{path}: unsupported TOML value type")

def _validate_value(value: Any, rule: FieldRule, path: str) -> None:
    expected = rule.value_type
    if type(value) not in (expected if isinstance(expected, tuple) else (expected,)):
        raise CometBFTProfileError(f"{path}: TOML value has wrong type")
    _validate_tree(value, path)

def _flatten(document: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in document.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict): result.update(_flatten(value, path))
        else: result[path] = value
    return result

def _utf16_sort_key(value: str) -> bytes:
    try: return value.encode("utf-16-be", errors="strict")
    except UnicodeEncodeError as exc: raise CometBFTProfileError("invalid Unicode scalar in profile key") from exc

def _canonical_json_subset(value: Any) -> bytes:
    """Canonical JSON for this module's restricted string/bool/safe-integer subset."""
    def ordered(node: Any) -> Any:
        if isinstance(node, dict): return {k: ordered(node[k]) for k in sorted(node, key=_utf16_sort_key)}
        if isinstance(node, list): return [ordered(item) for item in node]
        return node
    try:
        return json.dumps(ordered(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=False).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CometBFTProfileError("profile cannot be canonically serialized") from exc

def parse_cometbft_v040_profile(raw: bytes, schema: ProfileSchema) -> dict[str, Any]:
    """Strictly parse TOML and resolve only explicitly pinned schema defaults."""
    if type(raw) is not bytes or not raw or len(raw) > MAX_CONFIG_BYTES:
        raise CometBFTProfileError("config must be non-empty bytes no larger than 1 MiB")
    if raw.startswith(b"\xef\xbb\xbf"): raise CometBFTProfileError("UTF-8 BOM is not allowed")
    try: parsed = tomllib.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, RecursionError) as exc:
        raise CometBFTProfileError("invalid or unsafe TOML document") from exc
    if schema.source_commit != COMETBFT_V040_SOURCE_COMMIT or schema.complete is not True:
        raise CometBFTProfileError("complete schema pinned to CometBFT v0.40.0 is required")
    if not schema.fields: raise CometBFTProfileError("empty CometBFT schema")
    for path, rule in schema.fields.items():
        if not isinstance(path, str) or not path or rule.scope not in ("shared", "node_local", "software"):
            raise CometBFTProfileError("invalid source-derived schema entry")
        if rule.has_default: _validate_value(rule.default, rule, path)
    supplied = _flatten(parsed)
    unknown = set(supplied) - set(schema.fields)
    if unknown: raise CometBFTProfileError("unknown CometBFT TOML field: " + sorted(unknown)[0])
    normalized = {}
    for path, rule in schema.fields.items():
        if path in supplied: value = supplied[path]
        elif rule.has_default: value = copy.deepcopy(rule.default)
        else: raise CometBFTProfileError(f"required CometBFT TOML field missing: {path}")
        _validate_value(value, rule, path)
        normalized[path] = value
    return normalized

def cometbft_v040_profile_digest(normalized: Mapping[str, Any], schema: ProfileSchema) -> str:
    """Digest shared policy only; refuses partial or unpinned schemas."""
    if schema.source_commit != COMETBFT_V040_SOURCE_COMMIT or schema.complete is not True:
        raise CometBFTProfileError("complete pinned schema is required for profile digest")
    if set(normalized) != set(schema.fields): raise CometBFTProfileError("normalized profile/schema mismatch")
    shared = {path: normalized[path] for path, rule in schema.fields.items() if rule.scope == "shared"}
    if not shared: raise CometBFTProfileError("schema has no shared consensus profile fields")
    return hashlib.sha256(PROFILE_DOMAIN + _canonical_json_subset(shared)).hexdigest()
