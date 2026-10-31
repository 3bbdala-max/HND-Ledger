"""Deterministic local HND v0.2 block-chain reference.

Blocks link a sequence of locally validated ledger state transitions. This is
not peer-to-peer networking, distributed consensus, mining, or production code.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .genesis import validate_genesis_manifest
from .ledger import HNDLedger, LedgerError
from .transaction import ProtocolConfig, canonical_json

BLOCK_VERSION = 1
CHAIN_SNAPSHOT_VERSION = 1
MAX_BLOCK_TRANSACTIONS = 1000
MAX_TIMESTAMP_MS = (1 << 64) - 1
BLOCK_DOMAIN = b"HND-LEDGER/BLOCK\x00"
MERKLE_LEAF_DOMAIN = b"HND-LEDGER/MERKLE-LEAF\x00"
MERKLE_NODE_DOMAIN = b"HND-LEDGER/MERKLE-NODE\x00"
MERKLE_EMPTY_DOMAIN = b"HND-LEDGER/MERKLE-EMPTY\x00"
ZERO_HASH = "0" * 64
_HASH_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_HEADER_KEYS = {
    "block_version",
    "network_id",
    "protocol_version",
    "height",
    "timestamp_ms",
    "previous_block_hash",
    "genesis_hash",
    "transaction_count",
    "transaction_root",
    "state_hash",
}
_BLOCK_KEYS = {"header", "transactions", "block_hash"}
_CHAIN_SNAPSHOT_KEYS = {
    "schema_version",
    "network_id",
    "protocol_version",
    "genesis_hash",
    "blocks",
    "head_hash",
}


class BlockError(ValueError):
    """Raised when a block or local chain transition is invalid."""


def transaction_merkle_root(transactions: list[dict[str, Any]]) -> str:
    """Return a domain-separated Merkle root over full canonical tx envelopes.

    The signature is included because each leaf hashes the complete transaction
    JSON, not only the signature-excluded transaction identifier. An odd level
    duplicates its final node. The empty tree has a dedicated domain hash.
    """
    if type(transactions) is not list:
        raise ValueError("transactions must be a list")
    if not transactions:
        return hashlib.sha256(MERKLE_EMPTY_DOMAIN).hexdigest()

    level = [
        hashlib.sha256(MERKLE_LEAF_DOMAIN + canonical_json(tx)).digest()
        for tx in transactions
    ]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(MERKLE_NODE_DOMAIN + level[i] + level[i + 1]).digest()
            for i in range(0, len(level), 2)
        ]
    return level[0].hex()


def block_header_hash(header: Mapping[str, Any]) -> str:
    """Calculate the block hash from its complete canonical header."""
    if type(header) is not dict or set(header) != _HEADER_KEYS:
        raise ValueError("block header schema")
    return hashlib.sha256(BLOCK_DOMAIN + canonical_json(dict(header))).hexdigest()


def _copy_json(value: Any) -> Any:
    return json.loads(canonical_json(value).decode("utf-8"))


class HNDChain:
    """Single-process append-only sequence of blocks over the HND ledger model."""

    def __init__(self, *, config: ProtocolConfig, manifest: dict[str, Any],
                 expected_genesis_hash: str) -> None:
        ok, reason = validate_genesis_manifest(
            manifest, config=config, expected_genesis_hash=expected_genesis_hash
        )
        if not ok:
            raise BlockError(f"invalid genesis: {reason}")

        self.config = config
        self.manifest = _copy_json(manifest)
        self.genesis_hash = expected_genesis_hash
        self.ledger = HNDLedger(
            config=config, manifest=self.manifest,
            expected_genesis_hash=expected_genesis_hash,
        )
        self._blocks: list[dict[str, Any]] = []
        self._blocks.append(self._create_genesis_block())

    def _create_genesis_block(self) -> dict[str, Any]:
        header = {
            "block_version": BLOCK_VERSION,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "height": 0,
            "timestamp_ms": 0,
            "previous_block_hash": ZERO_HASH,
            "genesis_hash": self.genesis_hash,
            "transaction_count": 0,
            "transaction_root": transaction_merkle_root([]),
            "state_hash": self.ledger.snapshot()["state_hash"],
        }
        return {
            "header": header,
            "transactions": [],
            "block_hash": block_header_hash(header),
        }

    @property
    def blocks(self) -> list[dict[str, Any]]:
        """Return a detached copy so external callers cannot mutate chain history."""
        return _copy_json(self._blocks)

    @property
    def head_hash(self) -> str:
        return self._blocks[-1]["block_hash"]

    @property
    def height(self) -> int:
        return self._blocks[-1]["header"]["height"]

    def _clone_ledger(self) -> HNDLedger:
        return HNDLedger.restore(
            manifest=self.manifest,
            config=self.config,
            expected_genesis_hash=self.genesis_hash,
            snapshot=self.ledger.snapshot(),
        )

    def build_block(self, transactions: list[dict[str, Any]], *,
                    timestamp_ms: int) -> dict[str, Any]:
        """Validate a batch on a candidate ledger and append it as one block."""
        if type(transactions) is not list or not 1 <= len(transactions) <= MAX_BLOCK_TRANSACTIONS:
            raise BlockError("transaction count outside allowed range")
        if type(timestamp_ms) is not int or not 0 <= timestamp_ms <= MAX_TIMESTAMP_MS:
            raise BlockError("invalid timestamp")

        candidate = self._clone_ledger()
        normalized_transactions = _copy_json(transactions)
        try:
            for tx in normalized_transactions:
                candidate.apply_transaction(tx)
        except (LedgerError, TypeError, ValueError) as exc:
            raise BlockError(f"block transaction rejected: {exc}") from exc

        previous = self._blocks[-1]
        if timestamp_ms < previous["header"]["timestamp_ms"]:
            raise BlockError("timestamp moved backwards")

        header = {
            "block_version": BLOCK_VERSION,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "height": previous["header"]["height"] + 1,
            "timestamp_ms": timestamp_ms,
            "previous_block_hash": previous["block_hash"],
            "genesis_hash": self.genesis_hash,
            "transaction_count": len(normalized_transactions),
            "transaction_root": transaction_merkle_root(normalized_transactions),
            "state_hash": candidate.snapshot()["state_hash"],
        }
        block = {
            "header": header,
            "transactions": normalized_transactions,
            "block_hash": block_header_hash(header),
        }
        self.apply_block(block)
        return _copy_json(block)

    def apply_block(self, block: Any) -> str:
        """Validate a proposed next block completely before changing live state."""
        if type(block) is not dict or set(block) != _BLOCK_KEYS:
            raise BlockError("block schema")
        header = block["header"]
        transactions = block["transactions"]
        if type(header) is not dict or set(header) != _HEADER_KEYS:
            raise BlockError("block header schema")
        if type(transactions) is not list or not 1 <= len(transactions) <= MAX_BLOCK_TRANSACTIONS:
            raise BlockError("transaction count outside allowed range")

        if type(header["block_version"]) is not int or header["block_version"] != BLOCK_VERSION:
            raise BlockError("block version")
        if type(header["network_id"]) is not str or header["network_id"] != self.config.network_id:
            raise BlockError("block network")
        if type(header["protocol_version"]) is not int or header["protocol_version"] != self.config.protocol_version:
            raise BlockError("block protocol version")
        if type(header["height"]) is not int or header["height"] != self.height + 1:
            raise BlockError("block height")
        if type(header["timestamp_ms"]) is not int or not 0 <= header["timestamp_ms"] <= MAX_TIMESTAMP_MS:
            raise BlockError("invalid timestamp")
        if header["timestamp_ms"] < self._blocks[-1]["header"]["timestamp_ms"]:
            raise BlockError("timestamp moved backwards")
        if type(header["previous_block_hash"]) is not str or header["previous_block_hash"] != self.head_hash:
            raise BlockError("previous block hash mismatch")
        if type(header["genesis_hash"]) is not str or header["genesis_hash"] != self.genesis_hash:
            raise BlockError("genesis hash mismatch")
        if type(header["transaction_count"]) is not int or header["transaction_count"] != len(transactions):
            raise BlockError("transaction count mismatch")
        if type(header["transaction_root"]) is not str or not _HASH_RE.fullmatch(header["transaction_root"]):
            raise BlockError("transaction root format")
        if type(header["state_hash"]) is not str or not _HASH_RE.fullmatch(header["state_hash"]):
            raise BlockError("state hash format")
        if type(block["block_hash"]) is not str or not _HASH_RE.fullmatch(block["block_hash"]):
            raise BlockError("block hash format")

        try:
            actual_root = transaction_merkle_root(transactions)
            actual_block_hash = block_header_hash(header)
        except (TypeError, ValueError) as exc:
            raise BlockError("block encoding invalid") from exc
        if actual_root != header["transaction_root"]:
            raise BlockError("transaction root mismatch")
        if actual_block_hash != block["block_hash"]:
            raise BlockError("block hash mismatch")

        candidate = self._clone_ledger()
        try:
            for tx in transactions:
                candidate.apply_transaction(tx)
        except (LedgerError, TypeError, ValueError) as exc:
            raise BlockError(f"block transaction rejected: {exc}") from exc
        if candidate.snapshot()["state_hash"] != header["state_hash"]:
            raise BlockError("post-state hash mismatch")

        stored_block = _copy_json(block)
        self.ledger = candidate
        self._blocks.append(stored_block)
        return stored_block["block_hash"]

    def snapshot(self) -> dict[str, Any]:
        """Return chain data; each block carries its own transaction root and hash."""
        blocks_copy = _copy_json(self._blocks)
        return {
            "schema_version": CHAIN_SNAPSHOT_VERSION,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "genesis_hash": self.genesis_hash,
            "blocks": blocks_copy,
            "head_hash": self.head_hash,
        }

    @classmethod
    def restore(cls, *, manifest: dict[str, Any], config: ProtocolConfig,
                expected_genesis_hash: str, snapshot: Mapping[str, Any]) -> "HNDChain":
        """Rebuild the complete chain from Genesis by applying every stored block."""
        if type(snapshot) is not dict or set(snapshot) != _CHAIN_SNAPSHOT_KEYS:
            raise BlockError("chain snapshot schema")
        if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != CHAIN_SNAPSHOT_VERSION:
            raise BlockError("chain snapshot version")
        if type(snapshot["network_id"]) is not str or snapshot["network_id"] != config.network_id:
            raise BlockError("chain snapshot network")
        if type(snapshot["protocol_version"]) is not int or snapshot["protocol_version"] != config.protocol_version:
            raise BlockError("chain snapshot protocol version")
        if type(snapshot["genesis_hash"]) is not str or snapshot["genesis_hash"] != expected_genesis_hash:
            raise BlockError("chain snapshot genesis hash")
        if type(snapshot["blocks"]) is not list or not snapshot["blocks"]:
            raise BlockError("chain snapshot blocks")
        if type(snapshot["head_hash"]) is not str or not _HASH_RE.fullmatch(snapshot["head_hash"]):
            raise BlockError("chain snapshot head hash")

        chain = cls(
            config=config, manifest=manifest,
            expected_genesis_hash=expected_genesis_hash,
        )
        expected_genesis_block = chain._blocks[0]
        if canonical_json(snapshot["blocks"][0]) != canonical_json(expected_genesis_block):
            raise BlockError("genesis block mismatch")

        for index, block in enumerate(snapshot["blocks"][1:], start=1):
            try:
                chain.apply_block(block)
            except (BlockError, LedgerError, TypeError, ValueError) as exc:
                raise BlockError(f"chain block {index} rejected: {exc}") from exc

        if chain.head_hash != snapshot["head_hash"]:
            raise BlockError("chain head hash mismatch")
        return chain

    def save(self, path: str | os.PathLike[str]) -> None:
        """Atomically write the chain snapshot to a sibling temporary file."""
        destination = Path(path)
        if not destination.parent.exists() or not destination.parent.is_dir():
            raise FileNotFoundError("chain snapshot parent directory does not exist")
        encoded = json.dumps(
            self.snapshot(), sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False
        ) + "\n"
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=destination.parent,
                prefix=f".{destination.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temp_name = handle.name
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
            temp_name = None
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    @classmethod
    def load(cls, path: str | os.PathLike[str], *, manifest: dict[str, Any],
             config: ProtocolConfig, expected_genesis_hash: str) -> "HNDChain":
        """Load a JSON chain snapshot and verify every block from Genesis."""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                snapshot = json.load(
                    handle,
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise BlockError("chain snapshot cannot be decoded") from exc
        return cls.restore(
            manifest=manifest,
            config=config,
            expected_genesis_hash=expected_genesis_hash,
            snapshot=snapshot,
        )
