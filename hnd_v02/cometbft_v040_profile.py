"""Strict schema-driven CometBFT v0.40.0 TOML profile boundary."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from typing import Any, Mapping

COMETBFT_V040_SOURCE_COMMIT = "0880b4d378f347ab16e54ec677ff50d803f37d62"
PROFILE_DOMAIN = b"HND-COMETBFT-V040-PROFILE-v1\x00"
MAX_CONFIG_BYTES = 1_048_576
MAX_SCHEMA_BYTES = 4_194_304
MAX_INTEGER = (1 << 53) - 1
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class CometBFTProfileError(ValueError):
    """Fail-closed error at the CometBFT profile trust boundary."""


@dataclass(frozen=True)
class FieldRule:
    value_type: type | tuple[type, ...]
    scope: str
    default: Any = None
    has_default: bool = False
    item_type: type | tuple[type, ...] | None = None
    item_fields: Mapping[str, "FieldRule"] | None = None
    required: bool = True


@dataclass(frozen=True)
class ProfileSchema:
    source_commit: str
    fields: Mapping[str, FieldRule]
    complete: bool
    inventory_sha256: str = ""
    scope_manifest_sha256: str = ""
    rendered_template_sha256: str = ""
    scope_policy_reviewed: bool = False


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CometBFTProfileError("schema contains duplicate JSON object keys")
        result[key] = value
    return result


def _strict_json_object(raw: bytes, *, label: str, limit: int) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > limit:
        raise CometBFTProfileError(f"{label} must be non-empty bounded bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CometBFTProfileError(f"{label} must not contain a UTF-8 BOM")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_json_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CometBFTProfileError(f"{label} contains non-standard JSON constant")
            ),
        )
    except CometBFTProfileError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise CometBFTProfileError(f"{label} is not valid strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise CometBFTProfileError(f"{label} root must be an object")
    return value


def _python_type_from_go(go_type: str) -> type:
    # TOML values are interpreted according to the representation CometBFT's
    # own default config template emits, not just the Go field's underlying type.
    if go_type in ("string", "time.Duration"):
        return str
    if go_type == "bool":
        return bool
    if go_type in ("int", "int8", "int16", "int32", "int64",
                   "uint", "uint8", "uint16", "uint32", "uint64"):
        return int
    if go_type in ("float32", "float64"):
        return float
    raise CometBFTProfileError(f"unsupported Go field type in schema inventory: {go_type}")


def _type_from_toml_name(toml_type: str) -> type:
    mapping = {
        "string": str,
        "boolean": bool,
        "integer": int,
        "array": list,
    }
    try:
        return mapping[toml_type]
    except KeyError as exc:
        raise CometBFTProfileError(f"unsupported TOML type in schema inventory: {toml_type}") from exc


def _schema_field_rule(
    item: Mapping[str, Any],
    *,
    scope: str,
    path: str,
) -> FieldRule:
    go_type = item.get("go_type")
    toml_type = item.get("toml_type")
    if type(go_type) is not str or type(toml_type) is not str:
        raise CometBFTProfileError(f"{path}: schema field type metadata missing")
    if item.get("has_default") is not True or "default" not in item:
        raise CometBFTProfileError(f"{path}: generated TOML default is required")
    value_type = _type_from_toml_name(toml_type)
    default = item["default"]
    item_type_name = item.get("item_type")
    child_items = item.get("item_fields")
    item_type = None
    item_fields = None

    if toml_type == "array":
        if item_type_name == "table":
            if type(child_items) is not list or not child_items:
                raise CometBFTProfileError(f"{path}: array-of-table child schema missing")
            item_fields = {}
            for child in child_items:
                if type(child) is not dict:
                    raise CometBFTProfileError(f"{path}: invalid array-table field descriptor")
                child_name = child.get("name")
                child_go_type = child.get("go_type")
                required = child.get("required")
                if (
                    type(child_name) is not str or not child_name
                    or type(child_go_type) is not str
                    or type(required) is not bool
                    or child_name in item_fields
                ):
                    raise CometBFTProfileError(f"{path}: malformed array-table field descriptor")
                child_has_default = "default" in child
                if not required and not child_has_default:
                    raise CometBFTProfileError(
                        f"{path}.{child_name}: optional array-table field requires a default"
                    )
                item_fields[child_name] = FieldRule(
                    value_type=_python_type_from_go(child_go_type),
                    scope=scope,
                    default=copy.deepcopy(child.get("default")),
                    has_default=child_has_default,
                    required=required,
                )
            item_type = dict
        else:
            if type(item_type_name) is not str:
                raise CometBFTProfileError(f"{path}: array item type missing")
            item_type = _python_type_from_go(item_type_name)
            if child_items:
                raise CometBFTProfileError(f"{path}: primitive array cannot have item_fields")
    elif item_type_name is not None or child_items is not None:
        raise CometBFTProfileError(f"{path}: non-array field has array metadata")

    return FieldRule(
        value_type=value_type,
        scope=scope,
        default=copy.deepcopy(default),
        has_default=True,
        item_type=item_type,
        item_fields=item_fields,
    )


def load_cometbft_v040_profile_schema(
    inventory_raw: bytes,
    scope_manifest_raw: bytes,
) -> ProfileSchema:
    """Load a source-derived TOML inventory plus a separately reviewed scope policy.

    The inventory must be generated against the pinned CometBFT source by
    scripts/cometbft_v040_config_schema_dump.go. A schema is marked complete
    only if the policy explicitly attests review and classifies every inventory
    field exactly once, with the policy bound to the exact inventory bytes.
    """
    inventory = _strict_json_object(
        inventory_raw, label="CometBFT schema inventory", limit=MAX_SCHEMA_BYTES
    )
    policy = _strict_json_object(
        scope_manifest_raw, label="CometBFT profile scope manifest", limit=MAX_SCHEMA_BYTES
    )
    expected_inventory_keys = {
        "schema_version", "source_commit", "root_type",
        "rendered_template_sha256", "template_complete", "fields",
        "tables", "excluded_source_fields",
    }
    if set(inventory) != expected_inventory_keys:
        raise CometBFTProfileError("schema inventory key set mismatch")
    if (
        type(inventory["schema_version"]) is not int
        or inventory["schema_version"] != 1
        or inventory["source_commit"] != COMETBFT_V040_SOURCE_COMMIT
        or inventory["root_type"] != "config.Config"
        or inventory["template_complete"] is not True
    ):
        raise CometBFTProfileError("schema inventory is not complete for pinned CometBFT v0.40.0")
    if type(inventory["rendered_template_sha256"]) is not str or not _HEX64.fullmatch(
        inventory["rendered_template_sha256"]
    ):
        raise CometBFTProfileError("schema inventory template digest is invalid")
    if type(inventory["fields"]) is not list or not inventory["fields"]:
        raise CometBFTProfileError("schema inventory fields are missing")
    if (
        type(inventory["tables"]) is not list
        or any(type(value) is not str or not value for value in inventory["tables"])
        or inventory["tables"] != sorted(set(inventory["tables"]))
    ):
        raise CometBFTProfileError("schema inventory table list is invalid")
    if type(inventory["excluded_source_fields"]) is not list:
        raise CometBFTProfileError("schema inventory excluded-source list is invalid")
    excluded_go_paths = set()
    for excluded in inventory["excluded_source_fields"]:
        if (
            type(excluded) is not dict
            or set(excluded) != {"path", "go_path", "go_type", "reason"}
            or any(type(excluded[key]) is not str or not excluded[key] for key in excluded)
            or excluded["go_path"] in excluded_go_paths
        ):
            raise CometBFTProfileError("schema inventory excluded-source field is malformed")
        excluded_go_paths.add(excluded["go_path"])
    expected_tables = {
        ".".join(path.split(".")[:index])
        for entry in inventory["fields"]
        if type(entry) is dict and type(entry.get("path")) is str
        for index in range(1, len(entry["path"].split(".")))
    }
    if set(inventory["tables"]) != expected_tables:
        raise CometBFTProfileError("schema inventory table/field coverage mismatch")

    expected_policy_keys = {
        "schema_version", "source_commit", "inventory_sha256",
        "reviewed", "review_reference", "scopes",
    }
    if set(policy) != expected_policy_keys:
        raise CometBFTProfileError("scope manifest key set mismatch")
    if (
        type(policy["schema_version"]) is not int
        or policy["schema_version"] != 1
        or policy["source_commit"] != COMETBFT_V040_SOURCE_COMMIT
        or type(policy["reviewed"]) is not bool
        or type(policy["review_reference"]) is not str
        or type(policy["scopes"]) is not dict
    ):
        raise CometBFTProfileError("scope manifest metadata is invalid")

    inventory_digest = hashlib.sha256(inventory_raw).hexdigest()
    policy_inventory_digest = policy["inventory_sha256"]
    if type(policy_inventory_digest) is not str or not _HEX64.fullmatch(policy_inventory_digest):
        # An unbound/draft policy is allowed as an incomplete schema so that
        # tooling can display its gaps; it can never be accepted for hashing.
        policy_bound = False
    else:
        policy_bound = policy_inventory_digest == inventory_digest

    field_map: dict[str, Mapping[str, Any]] = {}
    go_paths = set()
    for entry in inventory["fields"]:
        if type(entry) is not dict:
            raise CometBFTProfileError("schema inventory field entry must be an object")
        required = {
            "path", "go_path", "go_type", "toml_type",
            "default", "has_default",
        }
        optional = {"item_type", "item_fields"}
        if not required.issubset(entry) or set(entry) - required - optional:
            raise CometBFTProfileError("schema inventory field descriptor key set mismatch")
        path = entry["path"]
        if (
            type(path) is not str or not path or path in field_map
            or type(entry["go_path"]) is not str or not entry["go_path"]
            or entry["go_path"] in go_paths
            or type(entry["go_type"]) is not str or not entry["go_type"]
            or type(entry["toml_type"]) is not str
            or entry["has_default"] is not True
            or "default" not in entry
        ):
            raise CometBFTProfileError("schema inventory has an invalid or duplicate field path")
        go_paths.add(entry["go_path"])
        field_map[path] = entry
    if list(field_map) != sorted(field_map):
        raise CometBFTProfileError("schema inventory fields are not in canonical path order")

    scopes = policy["scopes"]
    unknown_scopes = set(scopes) - set(field_map)
    if unknown_scopes:
        raise CometBFTProfileError("scope policy contains unknown field: " + sorted(unknown_scopes)[0])
    all_scopes_present = set(scopes) == set(field_map)
    valid_scope_values = all(
        type(value) is str and value in ("shared", "node_local", "software")
        for value in scopes.values()
    )
    complete = (
        policy["reviewed"] is True
        and bool(policy["review_reference"])
        and policy_bound
        and all_scopes_present
        and valid_scope_values
    )

    rules: dict[str, FieldRule] = {}
    for path, entry in field_map.items():
        scope = scopes.get(path, "unclassified")
        if scope not in ("shared", "node_local", "software"):
            scope = "unclassified"
        rules[path] = _schema_field_rule(entry, scope=scope, path=path)

    return ProfileSchema(
        source_commit=COMETBFT_V040_SOURCE_COMMIT,
        fields=rules,
        complete=complete,
        inventory_sha256=inventory_digest,
        scope_manifest_sha256=hashlib.sha256(scope_manifest_raw).hexdigest(),
        rendered_template_sha256=inventory["rendered_template_sha256"],
        scope_policy_reviewed=complete,
    )


def _validate_tree(value: Any, path: str) -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise CometBFTProfileError(f"{path}: invalid Unicode scalar") from exc
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_tree(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CometBFTProfileError(f"{path}: non-string key")
            _validate_tree(key, path)
            _validate_tree(item, f"{path}.{key}")
    elif value is None or isinstance(value, (bool, int)):
        if isinstance(value, int) and not isinstance(value, bool):
            if not -MAX_INTEGER <= value <= MAX_INTEGER:
                raise CometBFTProfileError(f"{path}: integer exceeds safe profile bound")
    else:
        raise CometBFTProfileError(f"{path}: unsupported TOML value type")


def _validate_value(value: Any, rule: FieldRule, path: str) -> None:
    expected = rule.value_type
    expected_types = expected if isinstance(expected, tuple) else (expected,)
    if type(value) not in expected_types:
        raise CometBFTProfileError(f"{path}: TOML value has wrong type")

    if not isinstance(value, list):
        _validate_tree(value, path)
        return

    if rule.item_fields is not None:
        normalized_items = []
        allowed = set(rule.item_fields)
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if type(item) is not dict:
                raise CometBFTProfileError(f"{item_path}: array-table item must be an object")
            unknown = set(item) - allowed
            if unknown:
                raise CometBFTProfileError(
                    f"{item_path}: unknown array-table field: " + sorted(unknown)[0]
                )
            normalized_item = {}
            for key, child_rule in rule.item_fields.items():
                if key in item:
                    child_value = item[key]
                elif child_rule.has_default:
                    child_value = copy.deepcopy(child_rule.default)
                elif child_rule.required:
                    raise CometBFTProfileError(f"{item_path}: required array-table field missing: {key}")
                else:
                    continue
                _validate_value(child_value, child_rule, f"{item_path}.{key}")
                normalized_item[key] = child_value
            normalized_items.append(normalized_item)
        # Normalize caller's list in place only in the local parsed tree. The
        # caller receives the fully default-resolved value for stable hashing.
        value[:] = normalized_items
    elif rule.item_type is not None:
        item_types = rule.item_type if isinstance(rule.item_type, tuple) else (rule.item_type,)
        for index, item in enumerate(value):
            if type(item) not in item_types:
                raise CometBFTProfileError(f"{path}[{index}]: array item has wrong type")
            _validate_tree(item, f"{path}[{index}]")
    else:
        raise CometBFTProfileError(f"{path}: array schema must declare item_type or item_fields")


def _table_paths(document: Mapping[str, Any], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key, value in document.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            paths.add(path)
            paths.update(_table_paths(value, path))
    return paths


def _flatten(document: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in document.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten(value, path))
        else:
            result[path] = value
    return result


def _utf16_sort_key(value: str) -> bytes:
    try:
        return value.encode("utf-16-be", errors="strict")
    except UnicodeEncodeError as exc:
        raise CometBFTProfileError("invalid Unicode scalar in profile key") from exc


def _canonical_json_subset(value: Any) -> bytes:
    """Canonical JSON for this module's restricted string/bool/safe-integer subset."""
    def ordered(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: ordered(node[key]) for key in sorted(node, key=_utf16_sort_key)}
        if isinstance(node, list):
            return [ordered(item) for item in node]
        return node

    try:
        return json.dumps(
            ordered(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CometBFTProfileError("profile cannot be canonically serialized") from exc


def parse_cometbft_v040_profile(raw: bytes, schema: ProfileSchema) -> dict[str, Any]:
    """Strictly parse TOML and resolve only explicitly pinned schema defaults."""
    if type(raw) is not bytes or not raw or len(raw) > MAX_CONFIG_BYTES:
        raise CometBFTProfileError("config must be non-empty bytes no larger than 1 MiB")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CometBFTProfileError("UTF-8 BOM is not allowed")
    try:
        parsed = tomllib.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, RecursionError) as exc:
        raise CometBFTProfileError("invalid or unsafe TOML document") from exc

    if schema.source_commit != COMETBFT_V040_SOURCE_COMMIT or schema.complete is not True:
        raise CometBFTProfileError("complete schema pinned to CometBFT v0.40.0 is required")
    if not schema.fields:
        raise CometBFTProfileError("empty CometBFT schema")
    for path, rule in schema.fields.items():
        if (
            not isinstance(path, str)
            or not path
            or rule.scope not in ("shared", "node_local", "software")
        ):
            raise CometBFTProfileError("invalid or unclassified source-derived schema entry")
        if rule.has_default:
            _validate_value(copy.deepcopy(rule.default), rule, path)

    supplied = _flatten(parsed)
    allowed_tables = {
        ".".join(path.split(".")[:index])
        for path in schema.fields
        for index in range(1, len(path.split(".")))
    }
    unknown_tables = _table_paths(parsed) - allowed_tables
    if unknown_tables:
        raise CometBFTProfileError("unknown CometBFT TOML table: " + sorted(unknown_tables)[0])
    unknown = set(supplied) - set(schema.fields)
    if unknown:
        raise CometBFTProfileError("unknown CometBFT TOML field: " + sorted(unknown)[0])

    normalized: dict[str, Any] = {}
    for path, rule in schema.fields.items():
        if path in supplied:
            value = supplied[path]
        elif rule.has_default:
            value = copy.deepcopy(rule.default)
        else:
            raise CometBFTProfileError(f"required CometBFT TOML field missing: {path}")
        _validate_value(value, rule, path)
        normalized[path] = value
    return normalized


def cometbft_v040_profile_digest(normalized: Mapping[str, Any], schema: ProfileSchema) -> str:
    """Digest shared policy only; refuses partial or unpinned schemas."""
    if schema.source_commit != COMETBFT_V040_SOURCE_COMMIT or schema.complete is not True:
        raise CometBFTProfileError("complete pinned schema is required for profile digest")
    if set(normalized) != set(schema.fields):
        raise CometBFTProfileError("normalized profile/schema mismatch")
    shared = {
        path: normalized[path]
        for path, rule in schema.fields.items()
        if rule.scope == "shared"
    }
    if not shared:
        raise CometBFTProfileError("schema has no shared consensus profile fields")
    return hashlib.sha256(PROFILE_DOMAIN + _canonical_json_subset(shared)).hexdigest()
