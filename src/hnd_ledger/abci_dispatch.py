"""Explicit ABCI request dispatcher for the HND v0.2 local application.

The dispatcher is intentionally narrow. Unsupported ABCI methods fail closed;
the Go transport layer must never receive fabricated success responses.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import threading
from collections import deque
from typing import Any

from .application import LedgerApplication
from .ipc_server import IPCError
from .protocol import CHAIN_ID, encode_transaction

EXTERNAL_CHAIN_ID = "HND-LOCAL-V2"
MAX_MEMPOOL_ITEMS = 10_000
MAX_MEMPOOL_BYTES = 8 * 1024 * 1024


def _bytes(payload: dict[str, Any], field: str, *, required: bool = True) -> bytes:
    value = payload.get(field)
    if value is None and not required:
        return b""
    if not isinstance(value, str):
        raise IPCError(f"{field} must be a base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise IPCError(f"{field} is not valid base64") from exc


def _integer(payload: dict[str, Any], field: str, *, minimum: int = 0) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise IPCError(f"{field} must be an integer >= {minimum}")
    return value


def _tx_list(payload: dict[str, Any]) -> tuple[bytes, ...]:
    values = payload.get("txs", [])
    if not isinstance(values, list):
        raise IPCError("txs must be an array")
    if len(values) > 1_000:
        raise IPCError("txs exceeds the block transaction limit")
    result = []
    for value in values:
        if not isinstance(value, str):
            raise IPCError("each transaction must be base64 text")
        try:
            result.append(base64.b64decode(value, validate=True))
        except (binascii.Error, ValueError) as exc:
            raise IPCError("transaction contains invalid base64") from exc
    return tuple(result)


class ABCIDispatcher:
    """Translate the small supported ABCI surface into ledger operations."""

    def __init__(self, application: LedgerApplication):
        self.application = application
        self._mempool: deque[bytes] = deque()
        self._mempool_bytes = 0
        self._mempool_lock = threading.Lock()

    def __call__(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_handle_{method}", None)
        if handler is None:
            raise NotImplementedError(f"ABCI method {method} is not implemented")
        return handler(payload)

    def _handle_Info(self, payload: dict[str, Any]) -> dict[str, Any]:
        info = self.application.info()
        return {
            "data": "HND deterministic local ledger",
            "version": "0.2.0",
            "app_version": 2,
            "last_block_height": info["last_block_height"],
            "last_block_app_hash": base64.b64encode(
                b"" if info["last_block_height"] == 0 else info["last_block_app_hash"]
            ).decode("ascii"),
        }

    def _handle_InitChain(self, payload: dict[str, Any]) -> dict[str, Any]:
        chain_id = payload.get("chain_id")
        if chain_id != EXTERNAL_CHAIN_ID or self.application.chain.state.chain_id != CHAIN_ID:
            raise IPCError("genesis chain ID does not match the HND local protocol")
        if self.application.height != 0 or self.application.chain.state.total_supply != 0:
            raise IPCError("InitChain only supports an empty height-zero development genesis")
        if self.application.chain.state.balances or self.application.chain.state.next_nonces:
            raise IPCError("development genesis must not contain preloaded account state")
        app_state = _bytes(payload, "app_state_bytes", required=False)
        if app_state:
            raise IPCError("non-empty app_state_bytes require an explicitly reviewed genesis schema")
        marker = hashlib.sha256(
            json.dumps({"chain_id": chain_id, "app_state_bytes": ""}, sort_keys=True).encode()
        ).digest()
        row = self.application.chain.db.execute(
            "SELECT value FROM metadata WHERE key='cometbft_genesis_marker'"
        ).fetchone()
        if row is not None and row[0] != marker:
            raise IPCError("a different CometBFT genesis was already initialized")
        if row is None:
            with self.application.chain.db:
                self.application.chain.db.execute(
                    "INSERT INTO metadata(key,value) VALUES('cometbft_genesis_marker',?)",
                    (marker,),
                )
        return {"validators": []}

    def _handle_CheckTx(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = _bytes(payload, "tx")
        try:
            self.application.check_tx(raw)
            return {"code": 0, "codespace": ""}
        except (ValueError, TypeError) as exc:
            return {"code": 1, "log": str(exc), "codespace": "hnd"}

    def _handle_InsertTx(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = _bytes(payload, "tx")
        try:
            self.application.check_tx(raw)
        except (ValueError, TypeError):
            return {"code": 1}
        with self._mempool_lock:
            if raw in self._mempool:
                return {"code": 0}
            if len(self._mempool) >= MAX_MEMPOOL_ITEMS or self._mempool_bytes + len(raw) > MAX_MEMPOOL_BYTES:
                return {"code": 2}
            self._mempool.append(raw)
            self._mempool_bytes += len(raw)
        return {"code": 0}

    def _handle_ReapTxs(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_bytes = _integer(payload, "max_bytes")
        with self._mempool_lock:
            selected = []
            used = 0
            for raw in self._mempool:
                if used + len(raw) > max_bytes:
                    break
                selected.append(base64.b64encode(raw).decode("ascii"))
                used += len(raw)
        return {"txs": selected}

    def _handle_PrepareProposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_bytes = _integer(payload, "max_tx_bytes")
        selected = self.application.prepare_proposal(_tx_list(payload))
        bounded = []
        used = 0
        for raw in selected:
            if used + len(raw) > max_bytes:
                break
            bounded.append(base64.b64encode(raw).decode("ascii"))
            used += len(raw)
        return {"txs": bounded}

    def _handle_ProcessProposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        accepted = self.application.process_proposal(_tx_list(payload))
        return {"status": 1 if accepted else 2}

    def _handle_FinalizeBlock(self, payload: dict[str, Any]) -> dict[str, Any]:
        height = _integer(payload, "height", minimum=1)
        if height != self.application.height + 1:
            raise IPCError("FinalizeBlock height is not the next application height")
        transactions = _tx_list(payload)
        app_hash = self.application.finalize_block(transactions)
        return {
            "tx_results": [{"code": 0} for _ in transactions],
            "validator_updates": [],
            "app_hash": base64.b64encode(app_hash).decode("ascii"),
        }

    def _handle_Commit(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._mempool_lock:
            included = {encode_transaction(tx) for tx in self.application._finalized.transactions} if self.application._finalized else set()
            self.application.commit()
            kept = deque(raw for raw in self._mempool if raw not in included)
            self._mempool = kept
            self._mempool_bytes = sum(map(len, kept))
        return {"retain_height": 0}
