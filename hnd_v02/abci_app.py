"""Python application-state lifecycle for the HND v0.2 ABCI++ adapter.

This module deliberately does not implement CometBFT consensus or its gRPC
transport. It provides deterministic HND state-transition methods that a
version-pinned ABCI server can call.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import secrets
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .ledger import HNDLedger, LedgerError
from .transaction import ProtocolConfig, canonical_json

APP_STORE_VERSION = 4
MAX_BLOCK_TRANSACTIONS = 1000
_STORE_KEYS = {
    "schema_version",
    "network_id",
    "protocol_version",
    "max_amount",
    "genesis_hash",
    "last_committed_height",
    "ledger_snapshot",
    "evidence_journal",
    "app_hash",
    "store_hash",
}


class ABCIApplicationError(ValueError):
    """Raised when an ABCI lifecycle transition cannot be applied safely."""


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate object keys instead of silently accepting the last value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


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
        require_existing_state: bool = False,
    ) -> None:
        self.config = config
        self.manifest = _json_copy(manifest)
        self.expected_genesis_hash = expected_genesis_hash
        self.state_path = Path(state_path)
        if type(require_existing_state) is not bool:
            raise TypeError("require_existing_state must be a bool")
        if self.state_path.name in ("", ".", ".."):
            raise ABCIApplicationError("application state path must name a file")

        directory_fd = self._open_state_directory()
        try:
            existing_state = self._stat_state_file(directory_fd)
            if require_existing_state and existing_state is None:
                raise ABCIApplicationError(
                    "recovery mode requires an existing application state file"
                )
        finally:
            os.close(directory_fd)

        self._lock = threading.RLock()
        self._committed_ledger = HNDLedger(
            config=config,
            manifest=self.manifest,
            expected_genesis_hash=expected_genesis_hash,
        )
        self._last_committed_height = 0
        self._evidence_journal: list[dict[str, Any]] = []
        self._committed_app_hash = self._calculate_app_hash(self._committed_ledger, self._evidence_journal)
        self._mempool_ledger = self._clone_committed()
        self._pending: dict[str, Any] | None = None
        self._initialized = False

        if existing_state is not None:
            self._load_store()

    def _open_state_directory(self) -> int:
        """Open the dedicated POSIX state directory without following its final symlink."""
        if (
            os.name != "posix"
            or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")
        ):
            raise ABCIApplicationError(
                "secure application state storage requires POSIX O_NOFOLLOW and directory-relative I/O"
            )
        try:
            directory_fd = os.open(
                self.state_path.parent,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise ABCIApplicationError(
                    "application state directory must be a real directory, not a symlink"
                ) from exc
            raise

        try:
            info = os.fstat(directory_fd)
            if not stat.S_ISDIR(info.st_mode):
                raise ABCIApplicationError("application state parent is not a directory")
            if info.st_uid != os.geteuid():
                raise ABCIApplicationError(
                    "application state directory must be owned by the service user"
                )
            if stat.S_IMODE(info.st_mode) != 0o700:
                raise ABCIApplicationError(
                    "application state directory must have mode 0700"
                )
            return directory_fd
        except Exception:
            os.close(directory_fd)
            raise

    @staticmethod
    def _validate_state_file_stat(info: os.stat_result) -> None:
        if stat.S_ISLNK(info.st_mode):
            raise ABCIApplicationError("application state file must not be a symlink")
        if not stat.S_ISREG(info.st_mode):
            raise ABCIApplicationError("application state path must be a regular file")
        if info.st_uid != os.geteuid():
            raise ABCIApplicationError(
                "application state file must be owned by the service user"
            )
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise ABCIApplicationError("application state file must have mode 0600")
        if info.st_nlink != 1:
            raise ABCIApplicationError("application state file must not have hard links")

    def _stat_state_file(self, directory_fd: int) -> os.stat_result | None:
        """Inspect the state entry without following symlinks."""
        try:
            info = os.stat(
                self.state_path.name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None
        self._validate_state_file_stat(info)
        return info

    def _open_state_file(self, directory_fd: int) -> int:
        """Open and validate the state file relative to its already-open directory."""
        try:
            file_fd = os.open(
                self.state_path.name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ABCIApplicationError(
                    "application state file must not be a symlink"
                ) from exc
            raise
        try:
            self._validate_state_file_stat(os.fstat(file_fd))
            return file_fd
        except Exception:
            os.close(file_fd)
            raise

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

    @staticmethod
    def _calculate_app_hash(ledger: HNDLedger, evidence_journal: list[dict[str, Any]]) -> str:
        payload = {"ledger_state_hash": ledger.state_hash, "evidence_journal": evidence_journal}
        return hashlib.sha256(b"HND-ABCI-APP-STATE-V1" + bytes((0,)) + canonical_json(payload)).hexdigest()

    @property
    def committed_state_hash(self) -> str:
        with self._lock:
            return self._committed_app_hash

    @property
    def evidence_journal(self) -> list[dict[str, Any]]:
        with self._lock:
            return _json_copy(self._evidence_journal)

    def evidence_page(self, *, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        """Return a bounded committed-evidence page and the total record count."""
        if type(offset) is not int or offset < 0:
            raise ABCIApplicationError("evidence offset must be a non-negative integer")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ABCIApplicationError("evidence limit must be an integer from 1 to 100")
        with self._lock:
            total = len(self._evidence_journal)
            page = self._evidence_journal[offset:offset + limit]
            return _json_copy(page), total

    def application_genesis_bytes(self) -> bytes:
        """Canonical HND application-state payload for CometBFT InitChain."""
        return canonical_json({
            "genesis_hash": self.expected_genesis_hash,
            "manifest": self.manifest,
            "protocol_config": {
                "network_id": self.config.network_id,
                "protocol_version": self.config.protocol_version,
                "max_amount": self.config.max_amount,
            },
        })

    def info(self) -> dict[str, Any]:
        """Return the durable recovery position and 32-byte application hash."""
        with self._lock:
            return {
                "last_block_height": self._last_committed_height,
                "last_block_app_hash": bytes.fromhex(self._committed_app_hash),
            }

    def init_chain(self, *, chain_id: str, app_state_bytes: bytes) -> None:
        """Verify the CometBFT chain identity and pinned HND Genesis payload."""
        with self._lock:
            if type(chain_id) is not str or chain_id != self.config.network_id:
                raise ABCIApplicationError("CometBFT chain_id does not match HND network_id")
            payload = _decode_canonical_object(app_state_bytes, label="application Genesis")
            if set(payload) != {"genesis_hash", "manifest", "protocol_config"}:
                raise ABCIApplicationError("application Genesis schema")
            expected_config = {
                "network_id": self.config.network_id,
                "protocol_version": self.config.protocol_version,
                "max_amount": self.config.max_amount,
            }
            if payload["protocol_config"] != expected_config:
                raise ABCIApplicationError("application Genesis protocol config mismatch")
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

    @staticmethod
    def _merge_evidence(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], block_height: int) -> list[dict[str, Any]]:
        records = {item["evidence_id"]: _json_copy(item) for item in existing}
        for item in incoming:
            required = {"type", "validator_address", "validator_power", "height", "time", "total_voting_power"}
            if type(item) is not dict or set(item) not in (required, required | {"evidence_id"}):
                raise ABCIApplicationError("misbehavior record schema")
            if type(item["type"]) is not int or item["type"] not in (1, 2):
                raise ABCIApplicationError("unsupported misbehavior type")
            address = item["validator_address"]
            if type(address) is not str or len(address) != 40 or any(c not in "0123456789abcdef" for c in address):
                raise ABCIApplicationError("invalid validator address")
            vp, total, infraction_height = item["validator_power"], item["total_voting_power"], item["height"]
            if type(vp) is not int or type(total) is not int or vp <= 0 or total <= 0 or vp > total:
                raise ABCIApplicationError("invalid misbehavior voting power")
            if type(infraction_height) is not int or infraction_height <= 0 or infraction_height >= block_height:
                raise ABCIApplicationError("invalid misbehavior infraction height")
            stamp = item["time"]
            if type(stamp) is not str:
                raise ABCIApplicationError("invalid misbehavior timestamp")
            try:
                parts = stamp.split(":")
                if len(parts) != 3 or parts[0] != "unix" or not parts[1].lstrip("-").isdigit() or len(parts[2]) != 9 or not parts[2].isdigit():
                    raise ValueError("timestamp must be unix seconds and nanoseconds")
                if int(parts[2]) >= 1_000_000_000 or stamp != f"unix:{int(parts[1])}:{int(parts[2]):09d}":
                    raise ValueError("timestamp is not canonical")
            except ValueError as exc:
                raise ABCIApplicationError("invalid misbehavior timestamp") from exc
            normalized = dict(item)
            identity = {"type": item["type"], "validator_address": address, "height": infraction_height}
            normalized["evidence_id"] = hashlib.sha256(b"HND-EVIDENCE-ID-V1" + bytes((0,)) + canonical_json(identity)).hexdigest()
            if "evidence_id" in item and item["evidence_id"] != normalized["evidence_id"]:
                raise ABCIApplicationError("evidence identifier mismatch")
            previous = records.get(normalized["evidence_id"])
            if previous is not None and previous != normalized:
                raise ABCIApplicationError("conflicting metadata for duplicate evidence")
            records[normalized["evidence_id"]] = normalized
        return [records[key] for key in sorted(records)]

    def finalize_block(self, *, height: int, transactions: list[bytes], misbehavior: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Execute the decided block in temporary state; do not persist it."""
        with self._lock:
            self._require_initialized()
            if self._pending is not None:
                raise ABCIApplicationError("previous finalized block has not been committed")
            if type(height) is not int or height != self._last_committed_height + 1:
                raise ABCIApplicationError("unexpected block height")
            self._validate_tx_list(transactions)
            if misbehavior is None:
                misbehavior = []
            if type(misbehavior) is not list:
                raise ABCIApplicationError("misbehavior must be a list")
            candidate_journal = self._merge_evidence(self._evidence_journal, misbehavior, height)

            candidate = self._clone_committed()
            results: list[dict[str, Any]] = []
            for raw in transactions:
                # Isolate each execution: a rejected transaction must not mutate
                # the candidate state used by later transactions in this block.
                trial = HNDLedger.restore(
                    manifest=self.manifest,
                    config=self.config,
                    expected_genesis_hash=self.expected_genesis_hash,
                    snapshot=candidate.snapshot(),
                )
                try:
                    txid = trial.apply_transaction(self._decode_tx(raw))
                except (ABCIApplicationError, LedgerError, TypeError, ValueError) as exc:
                    results.append({"code": 1, "data": b"", "log": str(exc)})
                    continue
                candidate = trial
                results.append({"code": 0, "data": bytes.fromhex(txid), "log": "ok"})

            app_hash = bytes.fromhex(self._calculate_app_hash(candidate, candidate_journal))
            self._pending = {
                "height": height,
                "ledger": candidate,
                "evidence_journal": candidate_journal,
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
            self._evidence_journal = pending["evidence_journal"]
            self._committed_app_hash = pending["app_hash"].hex()
            self._last_committed_height = pending["height"]
            self._mempool_ledger = self._clone_committed()
            self._pending = None
            return bytes(pending["app_hash"])

    def account_view(self, account_id: str) -> dict[str, int]:
        """Read only the last committed HND state, never a candidate or mempool view."""
        with self._lock:
            return self._committed_ledger.account_view(account_id)

    def _store_payload(self, ledger: HNDLedger, height: int, evidence_journal: list[dict[str, Any]]) -> dict[str, Any]:
        snapshot = ledger.snapshot()
        payload = {
            "schema_version": APP_STORE_VERSION,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "max_amount": self.config.max_amount,
            "genesis_hash": self.expected_genesis_hash,
            "last_committed_height": height,
            "ledger_snapshot": snapshot,
            "evidence_journal": _json_copy(evidence_journal),
            "app_hash": self._calculate_app_hash(ledger, evidence_journal),
        }
        # Bind recovery metadata (especially height) to the persisted snapshot.
        # This is an integrity checksum, not an authentication secret or MAC.
        payload["store_hash"] = hashlib.sha256(
            b"HND-ABCI-STORE-V2\\0" + canonical_json(payload)
        ).hexdigest()
        return payload

    def _write_store(self, ledger: HNDLedger, height: int) -> None:
        evidence = self._pending["evidence_journal"] if self._pending is not None and self._pending["ledger"] is ledger else self._evidence_journal
        payload = self._store_payload(ledger, height, evidence)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"

        directory_fd = self._open_state_directory()
        temp_name: str | None = None
        temp_fd: int | None = None
        try:
            # Refuse to replace an unsafe pre-existing entry.
            self._stat_state_file(directory_fd)
            for _ in range(16):
                candidate = f".hnd-state-{secrets.token_hex(12)}.tmp"
                try:
                    temp_fd = os.open(
                        candidate,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=directory_fd,
                    )
                    temp_name = candidate
                    break
                except FileExistsError:
                    continue
            if temp_fd is None or temp_name is None:
                raise FileExistsError("could not allocate a unique application state temp file")

            os.fchmod(temp_fd, 0o600)
            with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
                temp_fd = None
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                temp_name,
                self.state_path.name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            temp_name = None
            # Verify the installed entry and persist the directory rename.
            installed_state = self._stat_state_file(directory_fd)
            if installed_state is None:
                raise ABCIApplicationError("application state file missing after atomic replacement")
            os.fsync(directory_fd)
        finally:
            if temp_fd is not None:
                os.close(temp_fd)
            if temp_name is not None:
                try:
                    os.unlink(temp_name, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass
            os.close(directory_fd)

    def _load_store(self) -> None:
        directory_fd = self._open_state_directory()
        file_fd: int | None = None
        try:
            file_fd = self._open_state_file(directory_fd)
            with os.fdopen(file_fd, "r", encoding="utf-8") as handle:
                file_fd = None
                payload = json.load(
                    handle,
                    parse_constant=_reject_json_constant,
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
        except ABCIApplicationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ABCIApplicationError("application state file cannot be decoded") from exc
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(directory_fd)

        if type(payload) is not dict or set(payload) != _STORE_KEYS:
            raise ABCIApplicationError("application state file schema")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != APP_STORE_VERSION:
            raise ABCIApplicationError("application state file version")
        store_hash = payload["store_hash"]
        if (
            type(store_hash) is not str
            or len(store_hash) != 64
            or any(char not in "0123456789abcdef" for char in store_hash)
        ):
            raise ABCIApplicationError("application state store hash")
        unsigned_payload = {
            key: value for key, value in payload.items() if key != "store_hash"
        }
        expected_store_hash = hashlib.sha256(
            b"HND-ABCI-STORE-V2\\0" + canonical_json(unsigned_payload)
        ).hexdigest()
        if store_hash != expected_store_hash:
            raise ABCIApplicationError("application state store hash mismatch")
        if payload["network_id"] != self.config.network_id:
            raise ABCIApplicationError("application state network mismatch")
        if type(payload["protocol_version"]) is not int or payload["protocol_version"] != self.config.protocol_version:
            raise ABCIApplicationError("application state protocol mismatch")
        if type(payload["max_amount"]) is not int or payload["max_amount"] != self.config.max_amount:
            raise ABCIApplicationError("application state max_amount mismatch")
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
        journal = payload["evidence_journal"]
        if type(journal) is not list:
            raise ABCIApplicationError("application evidence journal schema")
        try:
            verified_journal = self._merge_evidence([], journal, height + 1)
        except ABCIApplicationError as exc:
            raise ABCIApplicationError("application evidence journal failed verification") from exc
        if canonical_json(verified_journal) != canonical_json(journal):
            raise ABCIApplicationError("application evidence journal is not canonical")
        expected_app_hash = self._calculate_app_hash(ledger, journal)
        if payload["app_hash"] != expected_app_hash:
            raise ABCIApplicationError("application state app hash mismatch")

        self._committed_ledger = ledger
        self._evidence_journal = journal
        self._committed_app_hash = expected_app_hash
        self._last_committed_height = height
        self._mempool_ledger = self._clone_committed()
        self._initialized = True
