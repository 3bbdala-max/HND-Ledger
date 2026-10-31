"""Deterministic genesis-manifest validation for the isolated HND v0.2 draft.

This module validates a proposed initial allocation document. It does not mint,
issue, distribute, or store balances and does not start a ledger.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from .transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    canonical_json,
    is_account_id_for_config,
)

GENESIS_DOMAIN = b"HND-LEDGER/GENESIS\x00"
_REQUIRED_MANIFEST_KEYS = {
    "manifest_version",
    "network_id",
    "protocol_version",
    "total_supply",
    "allocations",
}
_HASH_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


def genesis_manifest_hash(manifest: Mapping[str, Any]) -> str:
    """Hash the exact manifest bytes under the HND genesis domain."""
    if type(manifest) is not dict or set(manifest) != _REQUIRED_MANIFEST_KEYS:
        raise ValueError("schema")
    return hashlib.sha256(GENESIS_DOMAIN + canonical_json(dict(manifest))).hexdigest()


def validate_genesis_manifest(
    manifest: Any,
    *,
    config: ProtocolConfig,
    expected_genesis_hash: str,
) -> tuple[bool, str]:
    """Validate structure, deterministic order, allocations, supply sum, and pinned hash.

    The expected hash must be distributed through a trusted configuration or
    release process. Comparing a manifest to a hash supplied alongside that same
    untrusted manifest does not authenticate its origin.
    """
    if type(manifest) is not dict or set(manifest) != _REQUIRED_MANIFEST_KEYS:
        return False, "schema"

    if type(manifest["manifest_version"]) is not int or manifest["manifest_version"] != 1:
        return False, "manifest-version"
    if type(manifest["network_id"]) is not str or manifest["network_id"] != config.network_id:
        return False, "network-id"
    if type(manifest["protocol_version"]) is not int or manifest["protocol_version"] != config.protocol_version:
        return False, "protocol-version"
    if type(manifest["total_supply"]) is not int or manifest["total_supply"] <= 0:
        return False, "total-supply-type-or-range"

    allocations = manifest["allocations"]
    if type(allocations) is not list or not allocations:
        return False, "allocations"

    total = 0
    previous_account_id = None
    for item in allocations:
        if type(item) is not dict or set(item) != {"account_id", "public_key", "amount"}:
            return False, "allocation-schema"
        account_id = item["account_id"]
        amount = item["amount"]
        if not is_account_id_for_config(account_id, config=config):
            return False, "allocation-account-id"
        if previous_account_id is not None and account_id <= previous_account_id:
            return False, "allocation-order-or-duplicate"
        previous_account_id = account_id
        try:
            derived_account_id = account_id_for_public_key(item["public_key"], config=config)
        except (TypeError, ValueError):
            return False, "allocation-public-key"
        if account_id != derived_account_id:
            return False, "allocation-key-mismatch"
        if type(amount) is not int or amount <= 0:
            return False, "allocation-amount"
        total += amount

    if total != manifest["total_supply"]:
        return False, "allocation-sum"

    if type(expected_genesis_hash) is not str or not _HASH_RE.fullmatch(expected_genesis_hash):
        return False, "expected-genesis-hash"
    try:
        actual_hash = genesis_manifest_hash(manifest)
    except (TypeError, ValueError):
        return False, "manifest-encoding"
    if actual_hash != expected_genesis_hash:
        return False, "genesis-hash-mismatch"

    return True, "ok"
