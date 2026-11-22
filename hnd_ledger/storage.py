"""Crash-safe local SQLite storage with full deterministic chain replay.

This is a single-host reference store. SQLite transactions and FULL synchronous
WAL mode provide atomic local commits; this module is not distributed consensus.
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .blocks import ZERO_HASH, block_hash, create_genesis_block, decode_block_header, merkle_root, state_root
from .canonical import EncodingError, signed_transaction
from .chain import ChainError, build_block
from .decoder import decode_signed_transaction
from .ledger import Ledger, LedgerError, Transaction

STORE_FORMAT = b"HND-SQLITE-CHAIN-V1"
MAX_BLOCK_TRANSACTIONS = 100_000
MAX_TRANSACTION_BYTES = 1_048_576
MAX_BLOCK_TRANSACTION_BYTES = 67_108_864
MAX_SQLITE_INTEGER = (1 << 63) - 1


class StorageError(ValueError):
    """Persistent chain data is invalid or cannot be committed safely."""


def _state_bytes(balances: Mapping[str, int], nonces: Mapping[str, int]) -> bytes:
    payload = {
        "balances": dict(sorted(balances.items())),
        "nonces": dict(sorted(nonces.items())),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")


def _parse_state(encoded: bytes) -> tuple[dict[str, int], dict[str, int]]:
    try:
        payload = json.loads(encoded.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorageError("genesis state metadata is not valid canonical JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"balances", "nonces"}:
        raise StorageError("genesis state metadata has unexpected fields")
    balances, nonces = payload["balances"], payload["nonces"]
    if not isinstance(balances, dict) or not isinstance(nonces, dict):
        raise StorageError("genesis balances and nonces must be JSON objects")
    if _state_bytes(balances, nonces) != encoded:
        raise StorageError("genesis state metadata is not canonically encoded")
    try:
        Ledger(b"\x00" * 32, balances, nonces)
    except (LedgerError, TypeError) as exc:
        raise StorageError("genesis state metadata violates ledger rules") from exc
    return balances, nonces


def _encode_transactions(transactions: Sequence[Transaction]) -> bytes:
    if not isinstance(transactions, (list, tuple)):
        raise StorageError("transactions must be a list or tuple")
    if len(transactions) > MAX_BLOCK_TRANSACTIONS:
        raise StorageError("block transaction count exceeds local storage limit")
    chunks: list[bytes] = []
    total = 0
    for tx in transactions:
        if not isinstance(tx, Transaction):
            raise StorageError("block contains a non-Transaction object")
        try:
            encoded = signed_transaction(
                tx.chain_id,
                bytes.fromhex(tx.sender),
                bytes.fromhex(tx.recipient),
                tx.amount,
                tx.nonce,
                bytes.fromhex(tx.public_key),
                bytes.fromhex(tx.signature),
            )
        except (ValueError, EncodingError, TypeError) as exc:
            raise StorageError("transaction cannot be canonically encoded") from exc
        if len(encoded) > MAX_TRANSACTION_BYTES:
            raise StorageError("transaction exceeds local storage size limit")
        total += 4 + len(encoded)
        if total > MAX_BLOCK_TRANSACTION_BYTES:
            raise StorageError("block transaction payload exceeds local storage limit")
        chunks.append(len(encoded).to_bytes(4, "big") + encoded)
    return b"".join(chunks)


def _decode_transactions(encoded: bytes) -> tuple[Transaction, ...]:
    if not isinstance(encoded, bytes) or len(encoded) > MAX_BLOCK_TRANSACTION_BYTES:
        raise StorageError("stored transaction payload has invalid type or size")
    transactions: list[Transaction] = []
    offset = 0
    while offset < len(encoded):
        if len(encoded) - offset < 4:
            raise StorageError("truncated transaction length prefix")
        length = int.from_bytes(encoded[offset:offset + 4], "big")
        offset += 4
        if length == 0 or length > MAX_TRANSACTION_BYTES:
            raise StorageError("stored transaction length is outside local limits")
        end = offset + length
        if end > len(encoded):
            raise StorageError("truncated stored transaction")
        try:
            fields = decode_signed_transaction(encoded[offset:end])
            transactions.append(Transaction(
                chain_id=fields["chain_id"],
                sender=fields["sender"].hex(),
                recipient=fields["recipient"].hex(),
                amount=fields["amount"],
                nonce=fields["nonce"],
                public_key=fields["public_key"].hex(),
                signature=fields["signature"].hex(),
            ))
        except (EncodingError, KeyError, AttributeError, TypeError) as exc:
            raise StorageError("stored transaction is not canonical") from exc
        if len(transactions) > MAX_BLOCK_TRANSACTIONS:
            raise StorageError("stored block transaction count exceeds local limit")
        offset = end
    return tuple(transactions)


class SQLiteChainStore:
    """A local durable chain store that validates all blocks by replay.

    Create with a path, 32-byte chain ID, and genesis allocation map. Reopening
    requires the exact same chain ID and genesis allocation. Every append runs
    under BEGIN IMMEDIATE, replays the existing chain, validates the proposed
    block, and commits the complete block row in one SQLite transaction.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        chain_id: bytes,
        genesis_balances: Mapping[str, int],
    ) -> None:
        self.path = os.fspath(path)
        if self.path == ":memory:":
            raise StorageError("persistent storage requires a filesystem database path")
        if not isinstance(chain_id, bytes) or len(chain_id) != 32:
            raise StorageError("chain_id must be exactly 32 bytes")
        try:
            initial = Ledger(chain_id, genesis_balances)
            balances, nonces = initial.export_state()
            genesis = create_genesis_block(chain_id, balances)
        except (LedgerError, EncodingError, TypeError) as exc:
            raise StorageError("invalid genesis configuration") from exc
        self.chain_id = chain_id
        self._genesis_balances = balances
        self._genesis_nonces = nonces
        self._genesis_header = genesis["header"]
        self._genesis_hash = genesis["block_hash"]
        self._genesis_state = _state_bytes(balances, nonces)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self.path, timeout=30.0, isolation_level=None
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA busy_timeout = 30000")
            return connection
        except sqlite3.Error as exc:
            raise StorageError("could not open durable chain database") from exc

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata "
                "(key TEXT PRIMARY KEY, value BLOB NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS blocks ("
                "height INTEGER PRIMARY KEY CHECK(height > 0), "
                "header BLOB NOT NULL, "
                "block_hash BLOB NOT NULL UNIQUE, "
                "transactions BLOB NOT NULL)"
            )
            connection.execute("BEGIN IMMEDIATE")
            rows = dict(connection.execute("SELECT key, value FROM metadata"))
            expected = {
                "format": STORE_FORMAT,
                "chain_id": self.chain_id,
                "genesis_header": self._genesis_header,
                "genesis_hash": self._genesis_hash,
                "genesis_state": self._genesis_state,
            }
            if not rows:
                if connection.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]:
                    raise StorageError("database has blocks but no authenticated genesis metadata")
                connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES(?, ?)",
                    list(expected.items()),
                )
            elif rows != expected:
                raise StorageError("database belongs to a different or altered genesis")
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _genesis(self, connection: sqlite3.Connection) -> tuple[bytes, bytes, dict[str, int], dict[str, int]]:
        rows = dict(connection.execute("SELECT key, value FROM metadata"))
        required = {"format", "chain_id", "genesis_header", "genesis_hash", "genesis_state"}
        if set(rows) != required or rows["format"] != STORE_FORMAT:
            raise StorageError("database metadata is incomplete or has an unsupported format")
        if rows["chain_id"] != self.chain_id:
            raise StorageError("database chain ID mismatch")
        header = rows["genesis_header"]
        digest = rows["genesis_hash"]
        if not isinstance(digest, bytes) or len(digest) != 32:
            raise StorageError("stored genesis hash has invalid length")
        decoded = decode_block_header(header)
        if (
            decoded["chain_id"] != self.chain_id
            or decoded["height"] != 0
            or decoded["timestamp"] != 0
            or decoded["previous_hash"] != ZERO_HASH
            or decoded["transactions_root"] != merkle_root([])
            or decoded["transaction_count"] != 0
            or block_hash(header) != digest
        ):
            raise StorageError("stored genesis header or hash is invalid")
        balances, nonces = _parse_state(rows["genesis_state"])
        if state_root(balances, nonces) != decoded["state_root"]:
            raise StorageError("stored genesis state does not match its committed root")
        return header, digest, balances, nonces

    def _replay(
        self, connection: sqlite3.Connection
    ) -> tuple[bytes, bytes, dict[str, int], dict[str, int], int]:
        parent_header, parent_hash, balances, nonces = self._genesis(connection)
        expected_height = 1
        rows = connection.execute(
            "SELECT height, header, block_hash, transactions FROM blocks ORDER BY height"
        )
        for stored_height, header, digest, tx_blob in rows:
            if stored_height != expected_height:
                raise StorageError("stored block heights are not contiguous")
            if not isinstance(digest, bytes) or len(digest) != 32:
                raise StorageError("stored block hash has invalid length")
            try:
                candidate = decode_block_header(header)
                if candidate["height"] != expected_height:
                    raise StorageError("stored header height does not match its row")
                if candidate["previous_hash"] != parent_hash:
                    raise StorageError("stored block does not extend the verified parent")
                transactions = _decode_transactions(tx_blob)
                rebuilt = build_block(
                    parent_header, parent_hash, balances, nonces,
                    transactions, candidate["timestamp"],
                )
            except (EncodingError, ChainError, TypeError, ValueError) as exc:
                if isinstance(exc, StorageError):
                    raise
                raise StorageError(f"stored block {expected_height} failed replay") from exc
            if rebuilt["header"] != header or rebuilt["block_hash"] != digest:
                raise StorageError(f"stored block {expected_height} differs from replay")
            parent_header = header
            parent_hash = digest
            balances = rebuilt["balances"]
            nonces = rebuilt["nonces"]
            expected_height += 1
        return parent_header, parent_hash, balances, nonces, expected_height - 1

    def append_block(
        self, transactions: Sequence[Transaction], timestamp: int
    ) -> dict[str, Any]:
        """Atomically validate and persist one next block, returning its details."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            parent_header, parent_hash, balances, nonces, _ = self._replay(connection)
            block = build_block(
                parent_header, parent_hash, balances, nonces, transactions, timestamp
            )
            if block["height"] > MAX_SQLITE_INTEGER:
                raise StorageError("block height exceeds SQLite signed 64-bit integer range")
            tx_blob = _encode_transactions(transactions)
            connection.execute(
                "INSERT INTO blocks(height, header, block_hash, transactions) "
                "VALUES(?, ?, ?, ?)",
                (block["height"], block["header"], block["block_hash"], tx_blob),
            )
            connection.commit()
            return block
        except (sqlite3.Error, ChainError, EncodingError, LedgerError, TypeError, ValueError) as exc:
            if connection.in_transaction:
                connection.rollback()
            if isinstance(exc, StorageError):
                raise
            raise StorageError("block append was rejected; no partial block was committed") from exc
        finally:
            connection.close()

    def get_state(self) -> tuple[dict[str, int], dict[str, int]]:
        """Return defensive balance and nonce maps after full chain replay."""
        connection = self._connect()
        try:
            _, _, balances, nonces, _ = self._replay(connection)
            return dict(balances), dict(nonces)
        except (sqlite3.Error, EncodingError, ChainError, TypeError, ValueError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("could not reconstruct verified chain state") from exc
        finally:
            connection.close()

    def get_tip(self) -> dict[str, Any]:
        """Return the verified tip header, hash, height, balances, and nonces."""
        connection = self._connect()
        try:
            header, digest, balances, nonces, height = self._replay(connection)
            decoded = decode_block_header(header)
            return {
                "height": height,
                "header": header,
                "block_hash": digest,
                "timestamp": decoded["timestamp"],
                "balances": dict(balances),
                "nonces": dict(nonces),
            }
        except (sqlite3.Error, EncodingError, ChainError, TypeError, ValueError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("could not read verified chain tip") from exc
        finally:
            connection.close()

    def verify(self) -> bool:
        """Run SQLite's integrity check and replay every persisted block."""
        connection = self._connect()
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                return False
            self._replay(connection)
            return True
        except (sqlite3.Error, EncodingError, ChainError, StorageError, TypeError, ValueError):
            return False
        finally:
            connection.close()
