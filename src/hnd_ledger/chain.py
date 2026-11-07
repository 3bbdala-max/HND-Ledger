"""Deterministic blocks and replayable local chain storage."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .protocol import CHAIN_ID, PROTOCOL_VERSION, Transaction, canonical_cbor, decode_transaction, encode_transaction
from .state import LedgerError, LedgerState

BLOCK_PREFIX = b"HND-BLOCK-ID-V2\x00"
STATE_PREFIX = b"HND-STATE-V3\x00"
GENESIS_PREFIX = b"HND-GENESIS-V2\x00"
MAX_BLOCK_TRANSACTIONS = 1_000
MAX_BLOCK_BYTES = 65_536


class ChainError(ValueError):
    """Raised when block or persisted-chain validation fails."""


def state_commitment(state: LedgerState) -> bytes:
    accounts = sorted(set(state.balances) | set(state.next_nonces))
    rows = [
        [account, state.balances.get(account, 0), state.next_nonces.get(account, 0)]
        for account in accounts
    ]
    # Commit to every consensus-relevant state parameter, not only account rows.
    payload = [PROTOCOL_VERSION, state.chain_id, state.supply_cap, rows]
    return hashlib.sha256(STATE_PREFIX + canonical_cbor(payload)).digest()


@dataclass(frozen=True, slots=True)
class Block:
    height: int
    previous_hash: bytes
    transactions: tuple[bytes, ...]
    state_root: bytes
    block_hash: bytes


def _block_hash(height: int, previous_hash: bytes, transactions: tuple[bytes, ...], state_root: bytes) -> bytes:
    # The block commits to the exact canonical signed transaction bytes.
    payload = [PROTOCOL_VERSION, height, previous_hash, list(transactions), state_root]
    return hashlib.sha256(BLOCK_PREFIX + canonical_cbor(payload)).digest()


def _genesis_hash(chain_id: bytes, state: LedgerState) -> bytes:
    # Supply policy is part of genesis: identical balances with different caps
    # must never produce the same network identity.
    payload = [PROTOCOL_VERSION, chain_id, state.supply_cap, state_commitment(state)]
    return hashlib.sha256(GENESIS_PREFIX + canonical_cbor(payload)).digest()


class LocalChain:
    """SQLite-backed single-process chain; not a consensus implementation."""

    def __init__(self, path: str | Path, initial_state: LedgerState | None = None):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        try:
            self.db.execute("PRAGMA foreign_keys = ON")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value BLOB NOT NULL)"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS blocks (height INTEGER PRIMARY KEY, payload BLOB NOT NULL, block_hash BLOB NOT NULL UNIQUE)"
            )
            self.db.commit()
    
            row = self.db.execute("SELECT value FROM metadata WHERE key='genesis_state'").fetchone()
            if row is None:
                if initial_state is None:
                    raise ChainError("new chain requires an explicit initial state")
                if initial_state.chain_id != CHAIN_ID:
                    raise ChainError("initial state uses an unsupported chain id")
                self.state = LedgerState(
                    balances=dict(initial_state.balances),
                    next_nonces=dict(initial_state.next_nonces),
                    chain_id=initial_state.chain_id,
                    supply_cap=initial_state.supply_cap,
                )
                snapshot = canonical_cbor([
                    2, self.state.chain_id, self.state.supply_cap,
                    [[a, self.state.balances.get(a, 0), self.state.next_nonces.get(a, 0)]
                     for a in sorted(set(self.state.balances) | set(self.state.next_nonces))]
                ])
                self.db.execute("INSERT INTO metadata(key,value) VALUES('genesis_state',?)", (snapshot,))
                genesis_hash = _genesis_hash(self.state.chain_id, self.state)
                self.db.execute("INSERT INTO metadata(key,value) VALUES('genesis_hash',?)", (genesis_hash,))
                self.db.execute(
                    "INSERT INTO metadata(key,value) VALUES('chain_tip',?)",
                    (canonical_cbor([1, 0, genesis_hash]),),
                )
                self.db.execute(
                    "INSERT INTO metadata(key,value) VALUES('chain_tip_version',?)",
                    (canonical_cbor(1),),
                )
                self.db.commit()
            else:
                if initial_state is not None:
                    raise ChainError("initial state must not be supplied when reopening a chain")
                import cbor2
                decoded = cbor2.loads(row[0])
                if cbor2.dumps(decoded, canonical=True) != row[0]:
                    raise ChainError("non-canonical persisted genesis state")
                if not isinstance(decoded, list) or len(decoded) != 4 or decoded[0] != 2:
                    raise ChainError("invalid persisted genesis state")
                _, chain_id, supply_cap, rows = decoded
                self.state = LedgerState(
                    balances={r[0]: r[1] for r in rows if r[1] != 0},
                    next_nonces={r[0]: r[2] for r in rows if r[2] != 0},
                    chain_id=chain_id,
                    supply_cap=supply_cap,
                )
                genesis_row = self.db.execute("SELECT value FROM metadata WHERE key='genesis_hash'").fetchone()
                if genesis_row is None or genesis_row[0] != _genesis_hash(self.state.chain_id, self.state):
                    raise ChainError("persisted genesis commitment mismatch")
            self.blocks: list[Block] = []
            self._restore()
    
        except BaseException:
            # A failed constructor must not leave a live SQLite connection.
            self.db.close()
            raise

    def initialize_genesis(self, initial_state: LedgerState, *, marker: bytes | None = None) -> None:
        """Install an explicitly supplied genesis allocation before block 1.

        This is only permitted on a pristine zero-allocation chain. Reopening
        an initialized chain must use the persisted genesis and never replace it.
        """
        if not isinstance(initial_state, LedgerState):
            raise ChainError("genesis state must be a LedgerState")
        self._assert_tip_metadata()
        if self.height != 0 or self.state.total_supply != 0 or self.state.balances or self.state.next_nonces:
            raise ChainError("genesis allocations can only initialize a pristine empty chain")
        if initial_state.chain_id != self.state.chain_id:
            raise ChainError("genesis state uses a different chain id")
        candidate = LedgerState(
            balances=dict(initial_state.balances),
            next_nonces=dict(initial_state.next_nonces),
            chain_id=initial_state.chain_id,
            supply_cap=initial_state.supply_cap,
        )
        snapshot = canonical_cbor([
            2, candidate.chain_id, candidate.supply_cap,
            [[a, candidate.balances.get(a, 0), candidate.next_nonces.get(a, 0)]
             for a in sorted(set(candidate.balances) | set(candidate.next_nonces))]
        ])
        genesis_hash = _genesis_hash(candidate.chain_id, candidate)
        if marker is not None and (not isinstance(marker, bytes) or len(marker) != 32):
            raise ChainError("genesis marker must be 32 bytes")
        with self.db:
            for key, value in (
                ("genesis_state", snapshot),
                ("genesis_hash", genesis_hash),
                ("chain_tip", canonical_cbor([1, 0, genesis_hash])),
            ):
                cursor = self.db.execute(
                    "UPDATE metadata SET value=? WHERE key=?", (value, key)
                )
                if cursor.rowcount != 1:
                    raise ChainError(f"required genesis metadata is missing: {key}")
            if marker is not None:
                self.db.execute(
                    "INSERT INTO metadata(key,value) VALUES('cometbft_genesis_marker',?)",
                    (marker,),
                )
        self.state = candidate

    @property
    def tip_hash(self) -> bytes:
        if self.blocks:
            return self.blocks[-1].block_hash
        row = self.db.execute("SELECT value FROM metadata WHERE key='genesis_hash'").fetchone()
        return row[0]

    @property
    def height(self) -> int:
        return len(self.blocks)

    def checkpoint_ancestor_commitments(self, height: int) -> tuple[bytes, bytes]:
        """Return (block hash, app hash) at a locally replayed height.

        Height zero is represented by the genesis hash and the genesis-state
        commitment. Positive heights use the verified block hash and state
        root reconstructed during chain replay.
        """
        if isinstance(height, bool) or not isinstance(height, int) or height < 0:
            raise ChainError("checkpoint ancestor height must be a non-negative integer")
        if height > self.height:
            raise ChainError("checkpoint ancestor height exceeds local chain height")
        if height == 0:
            import cbor2

            row = self.db.execute(
                "SELECT value FROM metadata WHERE key='genesis_state'"
            ).fetchone()
            if row is None:
                raise ChainError("persisted genesis state is missing")
            try:
                decoded = cbor2.loads(row[0])
                if (not isinstance(decoded, list) or len(decoded) != 4
                        or decoded[0] != 2 or not isinstance(decoded[3], list)):
                    raise ChainError("persisted genesis state is malformed")
                _, chain_id, supply_cap, rows = decoded
                genesis_state = LedgerState(
                    balances={item[0]: item[1] for item in rows if item[1] != 0},
                    next_nonces={item[0]: item[2] for item in rows if item[2] != 0},
                    chain_id=chain_id,
                    supply_cap=supply_cap,
                )
                genesis_hash = _genesis_hash(chain_id, genesis_state)
                stored_hash = self.db.execute(
                    "SELECT value FROM metadata WHERE key='genesis_hash'"
                ).fetchone()
                if stored_hash is None or stored_hash[0] != genesis_hash:
                    raise ChainError("persisted genesis commitment mismatch")
                return genesis_hash, state_commitment(genesis_state)
            except ChainError:
                raise
            except Exception as exc:
                raise ChainError("unable to read genesis checkpoint commitments") from exc
        block = self.blocks[height - 1]
        return block.block_hash, block.state_root

    def _assert_tip_metadata(self) -> None:
        import cbor2

        version_row = self.db.execute(
            "SELECT value FROM metadata WHERE key='chain_tip_version'"
        ).fetchone()
        if version_row is None:
            raise ChainError("chain tip metadata version is missing")
        try:
            version = cbor2.loads(version_row[0])
            if (cbor2.dumps(version, canonical=True) != version_row[0]
                    or isinstance(version, bool) or version != 1):
                raise ChainError("unsupported chain tip metadata version")
        except ChainError:
            raise
        except Exception as exc:
            raise ChainError("invalid chain tip metadata version") from exc

        tip_row = self.db.execute(
            "SELECT value FROM metadata WHERE key='chain_tip'"
        ).fetchone()
        if tip_row is None:
            raise ChainError("persisted chain tip commitment is missing")
        try:
            raw = tip_row[0]
            anchor = cbor2.loads(raw)
            if (not isinstance(raw, bytes)
                    or cbor2.dumps(anchor, canonical=True) != raw
                    or not isinstance(anchor, list) or len(anchor) != 3
                    or isinstance(anchor[0], bool) or anchor[0] != 1
                    or isinstance(anchor[1], bool) or not isinstance(anchor[1], int)
                    or anchor[1] != self.height
                    or not isinstance(anchor[2], bytes) or anchor[2] != self.tip_hash):
                raise ChainError("persisted chain tip commitment mismatch")
        except ChainError:
            raise
        except Exception as exc:
            raise ChainError("invalid persisted chain tip commitment") from exc

    def append(self, transactions: Iterable[Transaction]) -> Block:
        self._assert_tip_metadata()
        txs = tuple(transactions)
        candidate = LedgerState(
            balances=dict(self.state.balances),
            next_nonces=dict(self.state.next_nonces),
            chain_id=self.state.chain_id,
            supply_cap=self.state.supply_cap,
        )
        if len(txs) > MAX_BLOCK_TRANSACTIONS:
            raise ChainError("block transaction count exceeds limit")
        encoded = tuple(encode_transaction(tx) for tx in txs)
        if sum(len(raw) for raw in encoded) > MAX_BLOCK_BYTES:
            raise ChainError("encoded block exceeds byte limit")
        for tx in txs:
            candidate.apply(tx)
        height = self.height + 1
        previous = self.tip_hash
        root = state_commitment(candidate)
        block_hash = _block_hash(height, previous, encoded, root)
        payload = canonical_cbor([2, height, previous, list(encoded), root, block_hash])
        if len(payload) > MAX_BLOCK_BYTES:
            raise ChainError("encoded block exceeds byte limit")
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO blocks(height,payload,block_hash) VALUES(?,?,?)",
                    (height, payload, block_hash),
                )
                cursor = self.db.execute(
                    "UPDATE metadata SET value=? WHERE key='chain_tip'",
                    (canonical_cbor([1, height, block_hash]),),
                )
                if cursor.rowcount != 1:
                    raise ChainError("chain tip commitment is missing; refusing block append")
        except sqlite3.IntegrityError as exc:
            raise ChainError("block persistence conflict") from exc
        block = Block(height, previous, encoded, root, block_hash)
        self.blocks.append(block)
        self.state = candidate
        return block

    def _restore(self) -> None:
        import cbor2
        previous = self.tip_hash
        for expected_height, (stored_height, stored_payload, stored_hash) in enumerate(
            self.db.execute("SELECT height, payload, block_hash FROM blocks ORDER BY height"), start=1
        ):
            if (isinstance(stored_height, bool) or not isinstance(stored_height, int)
                    or stored_height != expected_height):
                raise ChainError("stored block height sequence is invalid")
            payload = stored_payload
            try:
                if not isinstance(payload, bytes) or len(payload) > MAX_BLOCK_BYTES:
                    raise ChainError("persisted block exceeds byte limit")
                row = cbor2.loads(payload)
                if cbor2.dumps(row, canonical=True) != payload:
                    raise ChainError("non-canonical stored block")
                if not isinstance(row, list) or len(row) != 6:
                    raise ChainError("malformed stored block")
                version, height, prev_hash, tx_raws, root, claimed_hash = row
                if (isinstance(version, bool) or not isinstance(version, int) or version != PROTOCOL_VERSION
                        or isinstance(height, bool) or not isinstance(height, int) or height != expected_height
                        or not isinstance(prev_hash, bytes) or len(prev_hash) != 32 or prev_hash != previous
                        or not isinstance(root, bytes) or len(root) != 32
                        or not isinstance(claimed_hash, bytes) or len(claimed_hash) != 32):
                    raise ChainError("invalid block header or broken parent link")
                if not isinstance(tx_raws, list):
                    raise ChainError("block transactions must be an array")
                if len(tx_raws) > MAX_BLOCK_TRANSACTIONS or any(not isinstance(raw, bytes) for raw in tx_raws):
                    raise ChainError("block transaction count or encoding is invalid")
                txs = tuple(decode_transaction(raw, self.state.chain_id) for raw in tx_raws)
                candidate = LedgerState(
                    balances=dict(self.state.balances),
                    next_nonces=dict(self.state.next_nonces),
                    chain_id=self.state.chain_id,
                    supply_cap=self.state.supply_cap,
                )
                for tx in txs:
                    candidate.apply(tx)
                calculated_root = state_commitment(candidate)
                calculated_hash = _block_hash(height, prev_hash, tuple(tx_raws), calculated_root)
                if root != calculated_root or claimed_hash != calculated_hash or stored_hash != claimed_hash:
                    raise ChainError("stored block commitment mismatch")
                block = Block(height, prev_hash, tuple(tx_raws), root, claimed_hash)
                self.blocks.append(block)
                self.state = candidate
                previous = claimed_hash
            except Exception as exc:
                if isinstance(exc, ChainError):
                    raise
                # CBOR decoder errors are not consistently ValueError subclasses
                # across cbor2 versions; normalize all malformed-storage failures.
                raise ChainError("unable to restore persisted chain") from exc

        # A separate durable tip commitment detects deletion of the final
        # block, which replaying the remaining prefix alone cannot detect.
        tip_row = self.db.execute(
            "SELECT value FROM metadata WHERE key='chain_tip'"
        ).fetchone()
        actual_height = len(self.blocks)
        actual_hash = previous
        version_row = self.db.execute(
            "SELECT value FROM metadata WHERE key='chain_tip_version'"
        ).fetchone()
        if version_row is None:
            # One-time compatibility migration for pre-anchor databases. The
            # version marker makes deletion of the anchor detectable thereafter.
            with self.db:
                if tip_row is None:
                    self.db.execute(
                        "INSERT INTO metadata(key,value) VALUES('chain_tip',?)",
                        (canonical_cbor([1, actual_height, actual_hash]),),
                    )
                self.db.execute(
                    "INSERT INTO metadata(key,value) VALUES('chain_tip_version',?)",
                    (canonical_cbor(1),),
                )
            tip_row = self.db.execute(
                "SELECT value FROM metadata WHERE key='chain_tip'"
            ).fetchone()
        else:
            try:
                version_value = cbor2.loads(version_row[0])
                if (cbor2.dumps(version_value, canonical=True) != version_row[0]
                        or isinstance(version_value, bool) or version_value != 1):
                    raise ChainError("unsupported chain tip metadata version")
            except ChainError:
                raise
            except Exception as exc:
                raise ChainError("invalid chain tip metadata version") from exc
            if tip_row is None:
                raise ChainError("persisted chain tip commitment is missing")
        if tip_row is not None:
            try:
                anchor_value = tip_row[0]
                anchor = cbor2.loads(anchor_value)
                if (not isinstance(anchor_value, bytes)
                        or cbor2.dumps(anchor, canonical=True) != anchor_value
                        or not isinstance(anchor, list) or len(anchor) != 3
                        or isinstance(anchor[0], bool) or anchor[0] != 1
                        or isinstance(anchor[1], bool) or not isinstance(anchor[1], int)
                        or anchor[1] != actual_height
                        or not isinstance(anchor[2], bytes) or anchor[2] != actual_hash):
                    raise ChainError("persisted chain tip commitment mismatch")
            except ChainError:
                raise
            except Exception as exc:
                raise ChainError("invalid persisted chain tip commitment") from exc

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "LocalChain":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
