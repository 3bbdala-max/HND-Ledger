"""Python application-state lifecycle for the HND v0.2 ABCI++ adapter.

This module deliberately does not implement CometBFT consensus or its gRPC
transport. It provides deterministic HND state-transition methods that a
version-pinned ABCI server can call.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

from .ledger import HNDLedger, LedgerError
from .transaction import ProtocolConfig, canonical_json

APP_STORE_VERSION = 1
MAX_BLOCK_TRANSACTIONS = 1000
_STORE_KEYS = {
    "schema_version",
    "network_id",
    "protocol_version",
    "genesis_hash",
    "last_committed_height",
    "ledger_snapshot",
    "app_hash",
}


class ABCIApplicationError(ValueError):
    """Raised when an ABCI lifecycle transition cannot be applied safely."""


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _decode_canonical_object(raw: bytes, *, label: str) -> dict[str, Any]:
    """Decode an exact canonical JSON object; reject aliases and duplicate keys."""
    if type(raw) is not bytes or not raw:
        raise ABCIApplicationError(f"{label}: expected non-empty bytes")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ABCIApplicationError(f"{label}: invalid JSON") from exc
    if type(value) is not dict:
        raise ABCIApplicationError(f"{label}: expected JSON object")
    try:
        encoded = canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise ABCIApplicationError(f"{label}: unsupported JSON value") from exc
    if encoded != raw:
        raise ABCIApplicationError(f"{label}: non-canonical JSON")
    return value


def _json_copy(value: Any) -> Any:
    return json.loads(canonical_json(value).decode("utf-8"))


class HNDABCIApplication:
    """Deterministic HND application lifecycle, independent of ABCI transport.

    CometBFT is expected to own consensus and native block storage. This class
    owns only HND application state. Proposal validation uses temporary copies;
    only Commit atomically persists a finalized state.
    """

    def __init__(
        self,
        *,
        config: ProtocolConfig,
        manifest: dict[str, Any],
        expected_genesis_hash: str,
        state_path: str | os.PathLike[str],
    ) -> None:
        self.config = config
        self.manifest = _json_copy(manifest)
        self.expected_genesis_hash = expected_genesis_hash
        self.state_path = Path(state_path)
        if not self.state_path.parent.exists() or not self.state_path.parent.is_dir():
            raise FileNotFoundError("application state directory must already exist")

        self._lock = threading.RLock()
        self._committed_ledger = HNDLedger(
            config=config,
            manifest=self.manifest,
            expected_genesis_hash=expected_genesis_hash,
        )
        self._last_committed_height = 0
        self._mempool_ledger = self._clone_ledger(self._committed_ledger)
        self._pending: dict[str, Any] | None = None
        self._initialized = False

        if self.state_path.exists():
            self._load_store()

    @staticmethod
    def _clone_ledger(ledger: HNDLedger) -> HNDLedger:
        return HNDLedger.restore(
            manifest=ledger_manifest_placeholder,
            config=ledger.config,
            expected_genesis_hash=ledger.genesis_hash,
            snapshot=ledger.snapshot(),
        )

    def _clone_committed(self) -> HNDLedger:
        return HNDLedger.restore(
            manifest=self.manifest,
            config=self.config,
            expected_genesis_hash=self.expected_genesis_hash,
            snapshot=self._committed_ledger.snapshot(),
        )

    def _clone_mempool(self) -> HNDLedger:
        return HNDLedger.restore(
            manifest=self.manifest,
            config=self.config,
            expected_genesis_hash=self.expected_genesis_hash,
            snapshot=self._mempool_ledger.snapshot(),
        )

    @property
    def last_committed_height(self) -> int:
        with self._lock:
            return self._last_committed_height

    @property
    def committed_state_hash(self) -> str:
        with self._lock:
            return self._committed_ledger.state_hash

    def application_genesis_bytes(self) -> bytes:
        """Canonical HND application-state payload for CometBFT InitChain."""
        return canonical_json({
            "genesis_hash": self.expected_genesis_hash,
            "manifest": self.manifest,
        })

    def info(self) -> dict[str, Any]:
        """Return the durable recovery position and 32-byte application hash."""
        with self._lock:
            return {
                "last_block_height": self._last_committed_height,
                "last_block_app_hash": bytes.fromhex(self._committed_ledger.state_hash),
            }

    def init_chain(self, *, chain_id: str, app_state_bytes: bytes) -> None:
        """Verify the CometBFT chain identity and pinned HND Genesis payload."""
        with self._lock:
            if type(chain_id) is not str or chain_id != self.config.network_id:
                raise ABCIApplicationError("CometBFT chain_id does not match HND network_id")
            payload = _decode_canonical_object(app_state_bytes, label="application Genesis")
            if set(payload) != {"genesis_hash", "manifest"}:
                raise ABCIApplicationError("application Genesis schema")
            if payload["genesis_hash"] != self.expected_genesis_hash:
                raise ABCIApplicationError("application Genesis hash mismatch")
            if canonical_json(payload["manifest"]) != canonical_json(self.manifest):
                raise ABCIApplicationError("application Genesis manifest mismatch")

            if self._initialized:
                if self._last_committed_height == 0 and not self._committed_ledger.history:
                    return
                raise ABCIApplicationError("InitChain cannot replace an initialized application")
            self._write_store(self._committed_ledger, 0)
            self._initialized = True
            self._mempool_ledger = self._clone_committed()

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise ABCIApplicationError("application has not completed InitChain")

    @staticmethod
    def _decode_tx(raw: bytes) -> dict[str, Any]:
        return _decode_canonical_object(raw, label="transaction")

    @staticmethod
    def _validate_tx_list(transactions: Any) -> list[bytes]:
        if type(transactions) is not list:
            raise ABCIApplicationError("transactions must be a list")
        if len(transactions) > MAX_BLOCK_TRANSACTIONS:
            raise ABCIApplicationError("transaction count exceeds application limit")
        if any(type(tx) is not bytes or not tx for tx in transactions):
            raise ABCIApplicationError("each transaction must be non-empty bytes")
        return transactions

    def check_tx(self, tx_bytes: bytes, *, recheck: bool = False) -> dict[str, Any]:
        """Validate against an isolated mempool view, never the committed state."""
        del recheck  # NEW and RECHECK use the same deterministic admission rule.
        with self._lock:
            try:
                self._require_initialized()
                tx = self._decode_tx(tx_bytes)
                candidate = self._clone_mempool()
                txid = candidate.apply_transaction(tx)
                self._mempool_ledger = candidate
                return {"code": 0, "data": bytes.fromhex(txid), "log": "ok"}
            except (ABCIApplicationError, LedgerError, TypeError, ValueError) as exc:
                return {"code": 1, "data": b"", "log": str(exc)}

    def prepare_proposal(
        self, *, transactions: list[bytes], max_tx_bytes: int
    ) -> list[bytes]:
        """Return a deterministic valid subset within the supplied byte budget."""
        with self._lock:
            self._require_initialized()
            self._validate_tx_list(transactions)
            if type(max_tx_bytes) is not int or max_tx_bytes < 0:
                raise ABCIApplicationError("max_tx_bytes must be a non-negative integer")

            candidate = self._clone_committed()
            selected: list[bytes] = []
            selected_bytes = 0
            for raw in transactions:
                if selected_bytes + len(raw) > max_tx_bytes:
                    continue
                try:
                    trial = HNDLedger.restore(
                        manifest=self.manifest,
                        config=self.config,
                        expected_genesis_hash=self.expected_genesis_hash,
                        snapshot=candidate.snapshot(),
                    )
                    trial.apply_transaction(self._decode_tx(raw))
                except (ABCIApplicationError, LedgerError, TypeError, ValueError):
                    continue
                selected.append(raw)
                selected_bytes += len(raw)
                candidate = trial
            return selected

    def process_proposal(self, *, transactions: list[bytes]) -> dict[str, Any]:
        """Deterministically validate a proposal against the last committed state."""
        with self._lock:
            try:
                self._require_initialized()
                self._validate_tx_list(transactions)
                candidate = self._clone_committed()
                for raw in transactions:
                    candidate.apply_transaction(self._decode_tx(raw))
                return {"accepted": True, "reason": "ok"}
            except (ABCIApplicationError, LedgerError, TypeError, ValueError) as exc:
                return {"accepted": False, "reason": str(exc)}

    def finalize_block(self, *, height: int, transactions: list[bytes]) -> dict[str, Any]:
        """Execute the decided block in temporary state; do not persist it."""
        with self._lock:
            self._require_initialized()
            if self._pending is not None:
                raise ABCIApplicationError("previous finalized block has not been committed")
            if type(height) is not int or height != self._last_committed_height + 1:
                raise ABCIApplicationError("unexpected block height")
            self._validate_tx_list(transactions)

            candidate = self._clone_committed()
            results: list[dict[str, Any]] = []
            try:
                for raw in transactions:
                    txid = candidate.apply_transaction(self._decode_tx(raw))
                    results.append({"code": 0, "data": bytes.fromhex(txid), "log": "ok"})
            except (ABCIApplicationError, LedgerError, TypeError, ValueError) as exc:
                raise ABCIApplicationError(f"decided block contains invalid HND transaction: {exc}") from exc

            app_hash = bytes.fromhex(candidate.state_hash)
            self._pending = {
                "height": height,
                "ledger": candidate,
                "tx_results": results,
                "app_hash": app_hash,
            }
            return {
                "height": height,
                "tx_results": _json_copy([
                    {"code": item["code"], "data": item["data"].hex(), "log": item["log"]}
                    for item in results
                ]),
                "app_hash": app_hash,
            }

    def commit(self) -> bytes:
        """Atomically persist the pending state, then publish it as committed."""
        with self._lock:
            if self._pending is None:
                raise ABCIApplicationError("no finalized block is awaiting Commit")
            pending = self._pending
            self._write_store(pending["ledger"], pending["height"])
            self._committed_ledger = pending["ledger"]
            self._last_committed_height = pending["height"]
            self._mempool_ledger = self._clone_committed()
            self._pending = None
            return bytes(pending["app_hash"])

    def account_view(self, account_id: str) -> dict[str, int]:
        """Read only the last committed HND state, never a candidate or mempool view."""
        with self._lock:
            return self._committed_ledger.account_view(account_id)

    def _store_payload(self, ledger: HNDLedger, height: int) -> dict[str, Any]:
        snapshot = ledger.snapshot()
        return {
            "schema_version": APP_STORE_VERSION,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "genesis_hash": self.expected_genesis_hash,
            "last_committed_height": height,
            "ledger_snapshot": snapshot,
            "app_hash": snapshot["state_hash"],
        }

    def _write_store(self, ledger: HNDLedger, height: int) -> None:
        payload = self._store_payload(ledger, height)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.state_path.parent,
                prefix=f".{self.state_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_name = handle.name
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.state_path)
            temp_name = None
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    def _load_store(self) -> None:
        try:
            with self.state_path.open("r", encoding="utf-8") as handle:
                payload = json.load(
                    handle,
                    parse_constant=_reject_json_constant,
                )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ABCIApplicationError("application state file cannot be decoded") from exc

        if type(payload) is not dict or set(payload) != _STORE_KEYS:
            raise ABCIApplicationError("application state file schema")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != APP_STORE_VERSION:
            raise ABCIApplicationError("application state file version")
        if payload["network_id"] != self.config.network_id:
            raise ABCIApplicationError("application state network mismatch")
        if type(payload["protocol_version"]) is not int or payload["protocol_version"] != self.config.protocol_version:
            raise ABCIApplicationError("application state protocol mismatch")
        if payload["genesis_hash"] != self.expected_genesis_hash:
            raise ABCIApplicationError("application state Genesis mismatch")
        height = payload["last_committed_height"]
        if type(height) is not int or height < 0:
            raise ABCIApplicationError("application state height")
        if type(payload["app_hash"]) is not str or len(payload["app_hash"]) != 64:
            raise ABCIApplicationError("application state app hash")

        try:
            ledger = HNDLedger.restore(
                manifest=self.manifest,
                config=self.config,
                expected_genesis_hash=self.expected_genesis_hash,
                snapshot=payload["ledger_snapshot"],
            )
        except (LedgerError, TypeError, ValueError) as exc:
            raise ABCIApplicationError("application ledger snapshot failed verification") from exc
        if payload["app_hash"] != ledger.state_hash:
            raise ABCIApplicationError("application state app hash mismatch")

        self._committed_ledger = ledger
        self._last_committed_height = height
        self._mempool_ledger = self._clone_committed()
        self._initialized = True
