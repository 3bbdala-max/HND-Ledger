# HND v0.2 — WP4.2 application lifecycle core

**Date:** 2026-10-31  
**Workstream:** WP4.2 — ABCI application-state lifecycle core  
**Status:** Implemented and CI-tested; subsequently integrated with CometBFT v0.40.0 through WP4.3–WP4.8  
**Branch:** `phase-0.2-planning`

## 1. What was implemented

Added `hnd_v02/abci_app.py`, a transport-independent application lifecycle core intended to be called by a future version-pinned ABCI gRPC server.

It keeps the existing HND v0.2 ledger as the only transaction/state-transition implementation. It does not implement consensus, validator voting, P2P networking, CometBFT protobuf messages, or a network block history.

Implemented application operations:
- `info()`: last committed height and 32-byte application state hash.
- `application_genesis_bytes()` and `init_chain()`: canonical application Genesis payload, chain/network ID equality, and separately pinned Genesis hash verification.
- `check_tx()`: validates and advances an isolated mempool view, not committed state.
- `prepare_proposal()`: deterministically selects a valid ordered subset within a byte budget using temporary ledger copies.
- `process_proposal()`: validates a proposed transaction list deterministically against the last committed state, without state mutation.
- `finalize_block()`: executes the decided transaction list in a temporary ledger and returns the candidate application hash; it does not persist.
- `commit()`: atomically saves the finalized ledger and height, then publishes the new committed/mempool views.
- `account_view()`: reads committed balances only.

Application state uses the existing versioned HND ledger snapshot and replay-verified restore. The application hash is the existing deterministic HND ledger state hash, returned as 32 bytes. This hash is an application-state commitment, not a CometBFT block hash or a Merkle proof.

## 2. Isolation and safety properties

- Proposal processing never changes the committed HND ledger.
- Different proposals at one height use isolated candidate state.
- A finalized block remains pending until `commit()`.
- A restart before commit discards the uncommitted candidate and restores the last durable state.
- Failed disk replacement does not publish the candidate as committed; the pending candidate can be retried.
- After commit, the mempool view is rebuilt from the new committed state.
- Transaction JSON must be canonical; malformed and non-canonical encodings are rejected.
- An application-state file is restored by replaying signed HND history from the pinned Genesis manifest; stored balances are not trusted independently.
- Access to mutable application views is guarded by an in-process re-entrant lock.

These are properties of the tested application core. The actual ABCI server must still handle CometBFT's multiple concurrent connections and map every request/response correctly.

## 2.1 Subsequent durable-store hardening (2026-11-04)

The application store was advanced to schema version 2. Its persisted payload now contains a deterministic SHA-256 integrity checksum over the canonicalized schema version, network ID, protocol version, Genesis hash, committed height, ledger snapshot, and application hash. The loader validates the checksum before restoring the ledger. Persisted JSON is also decoded with duplicate-object-key rejection.

Two limits apply:

- This checksum detects accidental corruption or edits not accompanied by a recomputed checksum. It is **not** a keyed MAC, digital signature, or authenticity guarantee; an attacker able to rewrite the file can recompute an unkeyed SHA-256 checksum.
- Schema version 1 files are not automatically migrated by the current loader. A state upgrade requires a separately designed and validated migration process, or fresh approved Genesis for disposable test networks.

Regression tests cover invalid checksum format, metadata tampering, duplicate JSON keys, and deeper ledger/application-hash validation after deliberately resealing modified test fixtures.

## 3. Test coverage

Added `tests/test_v02_abci_app.py` initially with **31 targeted tests**; subsequent hardening expanded application and repository-wide coverage. The tests cover:
- correct/wrong chain ID and Genesis hash;
- canonical Genesis payload;
- Info height and application hash;
- mempool isolation, sequential nonce admission, duplicates, and malformed transactions;
- deterministic proposal preparation and transaction byte limits;
- valid/invalid proposals and conflicting nonces;
- candidate execution without premature persistence;
- height/order enforcement and pending-commit behavior;
- atomic commit, disk-write failure, restart recovery, and discarded uncommitted state;
- corrupted snapshot and application-hash rejection;
- query isolation from mempool/candidate state.

The full isolated v0.2 workflow completed successfully on code commit `fcc7928d0c1bb139ecb914c763923842571c29b4`:

**109 tests passed, 0 failed, in 16.927 seconds.**

Workflow (code fix and first successful run): https://github.com/3bbdala-max/HND-Ledger/actions/runs/41234032644

A second full CI run against the later documentation-updated branch head `77cf31812bee2effa228301d1b692b71ad6949e1` also completed successfully: **109 tests passed, 0 failed, in 16.494 seconds**.
Workflow: https://github.com/3bbdala-max/HND-Ledger/actions/runs/41234124803

The first run exposed a stale helper call left after cleanup; that failure was corrected before the successful run. The initial failure is retained in workflow history; it is not counted as a successful run.

## 4. Subsequent integration milestones (WP4.3–WP4.8)

The following work has since been implemented and CI-tested on `phase-0.2-planning`:

1. Python Protobuf/gRPC bindings generated from the pinned CometBFT v0.40.0 schema, and an ABCI gRPC servicer mapping the application lifecycle methods.
2. A real CometBFT v0.40.0 process connected to the HND application; CI covers handshake, Genesis initialization, transaction delivery, commit, restart, and application-hash recovery.
3. A disposable four-validator local network with separate CometBFT homes and separate HND application state files.
4. Four-validator crash-stop/restart catch-up and relay-backed 3/1 and 2/2 network-partition/reconnection tests.
5. A pinned FilePV signer smoke test covering conflicting votes/proposals at the same height/round/step and persistence of anti-double-sign state across restart.

The full workflow passed **133 Python tests** and the CometBFT single-node, signer-guard, four-validator Genesis/preflight, four-validator network, and partition/reconnection stages on commit `027a0db12ac391462ff97027df138491a3e83102`:
https://github.com/3bbdala-max/HND-Ledger/actions/runs/41723251514

This does **not** mean that every Byzantine behavior is tested. Deliberate malicious-validator behavior, 1/3+ fault scenarios, remote-signer security, snapshots/state sync, WAN behavior, and independent security review remain open.

## 5. Current next work

WP4.8's local FilePV guard is implemented and CI-verified. Next security work should exercise adversarial consensus-message and fault-injection scenarios against the four-validator harness, while preserving the distinction between CometBFT signer protections, consensus fault tolerance, and HND application transaction validation. Snapshot/state-sync support, production-grade storage, key custody, and external audit remain release gates.

## 6. Release boundary

This is still an experimental permissioned development network. No public network, public token issuance, sale, exchange listing, payment integration, custody, validator rewards, or real funds are authorized. No independent security audit, legal approval, or production readiness is claimed.
