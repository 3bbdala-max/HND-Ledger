# HND v0.2 — WP4.2 application lifecycle core

**Date:** 2026-10-31  
**Workstream:** WP4.2 — ABCI application-state lifecycle core  
**Status:** Implemented and CI-tested as a Python reference layer; not yet an ABCI server or CometBFT integration  
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

## 3. Test coverage

Added `tests/test_v02_abci_app.py` with **31 tests**, covering:
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

Workflow: https://github.com/3bbdala-max/HND-Ledger/actions/runs/41234032644

The first run exposed a stale helper call left after cleanup; that failure was corrected before the successful run. The initial failure is retained in workflow history; it is not counted as a successful run.

## 4. What is not yet implemented

This milestone does **not** yet include:
1. Python-generated Protobuf/gRPC stubs from the pinned CometBFT v0.40.0 `proto/tendermint/abci/types.proto`.
2. A Python gRPC `ABCI` servicer implementing the exact tagged request/response contract.
3. A real CometBFT process connecting to the application.
4. Correct end-to-end ABCI handshake / InitChain / Info / Query / Snapshot RPC interoperability.
5. Four independent validator processes, validator signing keys, or real consensus.
6. Network-partition, Byzantine-validator, crash/restart catch-up, or four-node convergence tests.

The 109 passing tests validate the application lifecycle core and the older v0.2 suites only. They do not validate CometBFT wire compatibility or multi-node consensus.

## 5. Next work

**WP4.3 — pinned ABCI gRPC transport adapter:**
1. Generate Python stubs exclusively from the v0.40.0 tagged Protobuf tree, not `main` or a different CometBFT/Cosmos SDK release.
2. Implement the required gRPC servicer methods and explicit conversions from generated Protobuf types to the tested core.
3. Add request/response tests for every method used by CometBFT v0.40.0.
4. Start one local CometBFT node against the Python application and prove the handshake, genesis initialization, one transaction, commit, restart, and app-hash handshake.
5. Only after the single-node path is stable, construct the disposable four-validator network.

## 6. Release boundary

This is an experimental local application adapter core. No public network, public token issuance, sale, exchange listing, payment integration, custody, validator rewards, or real funds are in scope. No independent security audit, legal approval, or production readiness is claimed.
