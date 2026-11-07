# HND-Ledger v0.2 — Reproducible test plan

## Evidence rule

A result is PASS only when the test, source commit, workflow run, and observed result are linked. Distinguish pass, fail, skipped, timed out, pending, and not run. Three or four processes on one CI runner are not independent operators.

## Verified CI evidence

- Python suite run 42368248628 on commit a76cee10eabafc7d27f36dbd66910f0f7feea790: PASS (77 tests).
- One-node CometBFT restart run 42368248709 on the same commit: PASS; node advanced from height 2 to 3 after all processes restarted with persistent data.
- Three-validator integration run 42368248612 on the same commit: PASS; signed transfer, Query, overspend filtering, matching app hashes, and validator-0 restart recovery.
- Four-validator liveness run 42368248630 on the same commit: PASS; validators 1–3 advanced from height 3 to at least height 5 while validator 0 was offline; restarted validator 0 caught up; all four app hashes matched at height 5.
- Go adapter tests/static analysis run 42359852685 on commit 1c62d3cad548315b8cecb811edd76ee6b93808af: PASS.

## Unit test coverage

Python tests cover canonical CBOR and base64, Ed25519 verification, chain separation, malformed encodings, replay, nonce gaps/conflicts/overflow, self-transfer, overspend, balance overflow, supply cap, duplicate transactions, atomic proposals, genesis validation/idempotence, conflicting-genesis rejection, atomic genesis marker persistence, state commitment coverage, block hashes, SQLite restore/replay, IPC validation, and read-only Query responses.

The dispatcher tests confirm weak CheckTx accepts a well-formed signed overspend, while PrepareProposal filters it without changing committed state and still selects a valid following transaction. CheckTx RECHECK is state-aware: after a block commits, stale transactions that no longer satisfy balance/nonce rules are rejected, while still-valid transactions are retained; recheck does not mutate committed state. Mempool tests cover item and byte ceilings, duplicate submissions without double-counting bytes, capacity rejection, and capacity reuse after Commit evicts included transactions.

Persistence tests include SQLite trigger aborts during block insertion and before/after insertion of the CometBFT genesis marker, plus child processes terminated inside uncommitted SQLite transactions. Reopening verifies rollback to the original genesis state with no partial block or marker. The suite also checks that a funded-genesis retry after restart is idempotent and a different genesis cannot mutate the persisted state.

Go tests cover IPC request correlation, malformed/mismatched responses, typed errors, partial writes, zero-progress writes, and loopback listener validation. Go static analysis runs in CI.

## Integration matrix

| ID | Scenario | Evidence |
|---|---|---|
| INT-01 | One-node CometBFT startup and block production | PASS, run 42368248709, commit a76cee10 |
| INT-02 | One-node restart with persistent data and resumed block production | PASS, run 42368248709, commit a76cee10 |
| INT-03 | Three validators reach common height | PASS, run 42368248612, commit a76cee10 |
| INT-04 | Funded test genesis and signed transfer | PASS, run 42368248612, commit a76cee10 |
| INT-05 | Matching balances, nonce, and state commitment | PASS, run 42368248612, commit a76cee10 |
| INT-06 | Matching post-transfer CometBFT app hash | PASS, run 42368248612, commit a76cee10 |
| INT-07 | Restarted validator retains transfer and state | PASS, run 42368248612, commit a76cee10 |
| INT-08 | Account and ledger-info queries through all three RPC endpoints | PASS, run 42368248612, commit a76cee10 |
| INT-09 | Signed overspend admitted by weak CheckTx but filtered before proposal commit on all validators | PASS, run 42368248612, commit a76cee10 |
| INT-10 | Identical funded-genesis retry after application restart | PASS, run 42362574022 |
| INT-11 | Conflicting funded-genesis request rejected after restart without state mutation | PASS, run 42362574022 |
| INT-12 | Non-canonical base64 genesis payload rejected without writing marker or allocations | PASS, run 42362574022 |
| INT-13 | Mempool item/byte caps, duplicate accounting, and committed-entry capacity release | PASS, run 42365173568 |
| INT-14 | CheckTx RECHECK rejects stale balance/nonce transactions after commit without mutating state | PASS, Python regression suite run 42365922063 |
| INT-15 | Four-validator quorum continues with one validator stopped; restarted validator catches up and all app hashes agree | PASS, run 42368248630, commit a76cee10; common height 5, app hash 2FA595F9328078EB77A6EE62BDAD3743D619B1371BB82DD78AD0D98FAECC03A9 |
| INT-16 | Live network partition: validator 0 remains running but has zero peers; validators 1–3 retain two peers each and advance from height 7 to 12 | PASS, run 42377936382, commit 747560b396344d89d3fb223fe12ee29c95684a0c; single CI runner | 
| INT-17 | Heal partition; validator 0 catches up and all four app hashes agree at height 12 | PASS, run 42377936382, commit 747560b396344d89d3fb223fe12ee29c95684a0c; app hash 2FA595F9328078EB77A6EE62BDAD3743D619B1371BB82DD78AD0D98FAECC03A9 |

## Latest exact-commit CI evidence

All five workflows completed successfully on code commit `95f6ffb996e77661c809f536981461558d56640a`:
- HND tests run `42380149853`: PASS.
- Go adapter and FilePV process-exit test run `42380149848`: PASS; `go test ./...`, `go vet ./...`, and `internal/consensusguard` passed.
- One-node CometBFT restart run `42380149862`: PASS.
- Three-validator integration run `42380149798`: PASS.
- Four-validator liveness/partition recovery run `42380149833`: PASS.

The docs-only follow-up commit `2f235ce9bdbf4cd82f4bf2dbd3e1b4ae024e4bd4` also completed all five workflows successfully: HND tests `42380193749`, one-node `42380193790`, three-validator `42380193834`, four-validator `42380193851`; the Go adapter is unchanged from the passing `95f6ffb...` code commit.

All five CI paths completed successfully on commit `54229259b05ed322f94deaaf87abf532c788c5b3`:
- Python tests run `42378294082`: PASS.
- Go adapter tests and `go vet` run `42378294015`: PASS; logs show `internal/consensusguard` tests passed.
- One-node CometBFT restart run `42378294051`: PASS.
- Three-validator integration run `42378294043`: PASS.
- Four-validator liveness and live partition/recovery run `42378294063`: PASS.

The Go suite on `54229259...` includes a FilePV reload unit test proving same-vote signature reuse and conflicting-vote rejection. The follow-up on `95f6ffb996e77661c809f536981461558d56640a` passed in Go adapter run `42380149848` (job `128425864594`): a child signing process exits immediately after signing/persisting, then a parent reloads FilePV state, verifies identical signature reuse, and confirms a conflicting vote is rejected. `go test ./...` and `go vet ./...` both passed. This remains a targeted FilePV process-exit test, not a full CometBFT node crash/restart integration test.

All four workflows completed successfully on code commit `a76cee10eabafc7d27f36dbd66910f0f7feea790`:
- Python tests run `42368248628`: PASS (77 tests).
- One-node CometBFT restart run `42368248709`: PASS.
- Three-validator integration run `42368248612`: PASS; signed transfer, RPC queries, overspend filtering, state/app-hash consistency, and restart recovery.
- Four-validator liveness run `42368248630`: PASS; three validators continued producing blocks while the fourth was stopped, and the restarted validator caught up with matching app hash.

## Live partition evidence

On commit `747560b396344d89d3fb223fe12ee29c95684a0c`, workflow run `42377936382` completed successfully. The four validators ran as separate processes and data directories on one GitHub Actions runner. Validator 0 stayed running with zero P2P peers at height 7; validators 1–3 each retained two peers and advanced to height 12. After the partition healed, validator 0 caught up and all four app hashes matched at height 12 (`2FA595F9328078EB77A6EE62BDAD3743D619B1371BB82DD78AD0D98FAECC03A9`). This proves the tested local scenario only, not independent-host fault tolerance.

## Remaining adversarial and operational tests

Live partition and healing are now verified on one CI runner (INT-16/INT-17); independent multi-host partition testing remains unverified. Conflicting proposals, equivocation, replayed votes, Byzantine voting-power scenarios, validator crash after signing, validator-set updates, state sync, snapshot integrity, database rollback detection, backup/restore, multi-host deployment, mempool flooding, per-peer quotas, CPU/memory exhaustion, and crash injection around every SQLite commit boundary remain unverified.

## Exact-commit verification after P2P mesh-readiness correction

All four workflows completed successfully on code commit `41c4eeb4cb61c34b8f1caf4f454de346a06a3a60`:
- Python tests run `42382470345`: PASS.
- One-node CometBFT restart run `42382470355`: PASS.
- Three-validator integration run `42382470350`: PASS.
- Four-validator liveness and recovery run `42382470318`: PASS. The workflow now waits up to 90 seconds for every validator to establish all three P2P peers before beginning the partition scenario; the complete liveness/recovery scenario then passed.

The Python dispatcher regression test on commit `0ab7294c52f12366aea99a55564b063896e82294`, run `42381330354`, confirms vote-extension and snapshot methods raise explicit unsupported-method errors. The same Python suite passed again on `41c4eeb4...` in run `42382470345`.

## v0.2 feature boundary

Validator membership is fixed at genesis for this release candidate. Dynamic validator-set updates, vote extensions, snapshots, and state sync are not implemented features. Unsupported vote-extension and snapshot methods fail closed. The four-validator partition test uses four processes/data directories on one CI runner; independent multi-host/multi-operator validation remains open.


## IPC stalled-client regression and exact-commit verification

On code/test commit `a7665df2edcd18ea15417640593eefd7d994ed0d`, Python workflow run `42382630569` passed, including `test_incomplete_client_cannot_block_following_ipc_request`. The test holds one Unix-socket client after a partial JSON frame and verifies that a subsequent valid Info request is served after the configured read deadline. The implementation sets a 5-second request read timeout and closes/logs incomplete clients.

The four integration workflows on the same exact commit all completed successfully:
- Python suite and IPC timeout regression: run `42382630569`, PASS.
- One-node CometBFT restart: run `42382630603`, PASS.
- Three-validator integration: run `42382630560`, PASS.
- Four-validator liveness and recovery: run `42382630546`, PASS.

This establishes the tested single-client timeout behavior and integration regression coverage. It does not establish connection-rate protection, per-peer quotas, multi-client flood resistance, or CPU/memory exhaustion resistance.


## Concurrent IPC burst regression

The concurrent local IPC regression was increased from 16 to 32 clients on commit `7e86e0a21a7e51033d44471376cef45b346b2f40`. All four workflows passed on that exact commit: Python run `42391236132`, one-node CometBFT run `42391236205`, three-validator run `42391236154`, and four-validator liveness/recovery run `42391236188`. The Python test checks that all 32 short requests receive successful responses with the correct request IDs and client payloads. It does not establish sustained throughput, overload behavior, or denial-of-service resistance.

The IPC burst regression was then increased to 64 clients and 64 worker threads on code/test commit `bf3f38a79c9bd21ec8079a70a3cc665d91fcb5ec`. All four workflows passed on that exact commit: Python run `42395157838`, one-node CometBFT run `42395157660`, three-validator run `42395157576`, and four-validator liveness/recovery run `42395157681`. The test verifies 64 successful short responses with exact request-ID and payload correlation. This remains a bounded burst regression, not a sustained-load, throughput-capacity, or flood-resistance benchmark.

## Mempool aggregate capacity regression

The mempool capacity regression was strengthened on code/test commit `f4d4400746588c29addf1da83f921c4ec113b2ec`. Python workflow run `42395627611` passed, as did the one-node CometBFT run `42395627641`, three-validator run `42395627541`, and four-validator liveness/recovery run `42395627524`, all on that exact commit. The test verifies rejection above the byte ceiling, acceptance at the exact aggregate byte boundary, rejection when the next transaction exceeds remaining byte capacity, duplicate submissions without double-counting, partial eviction of only transactions included in a committed block, byte-capacity reuse after subsequent commit, and independent item-count enforcement. This is deterministic bounded-capacity coverage, not sustained adversarial-load or denial-of-service testing; the existing 10,000-item / 8 MiB limits remain configuration bounds rather than a throughput claim.


## Maximum byte-bounded concurrent mempool batch

On code/test commit `a70217e61756391c9ab0a4c37245d7d05715eae8`, all four exact-commit workflows passed: Python tests run `42399167647`, one-node CometBFT run `42399167635`, three-validator run `42399167682`, and four-validator liveness/recovery run `42399167636`. The regression constructs nonce-ordered signed transfers until the complete canonical CBOR block would reach its configured byte ceiling, concurrently inserts the batch with 32 workers, verifies exact mempool byte accounting and proposal nonce order, then finalizes and commits the full batch and checks balances/nonces and mempool eviction. The test measures the encoded block envelope as well as transaction bytes. This is bounded maximum-byte regression coverage, not a sustained throughput benchmark, a 1,000-transaction proof, or an adversarial flood-resistance test.


## Chain-tip metadata migration and corruption regressions

On code/test commit `9a38f5b008f198c4039b76454ef41b2c48985488`, the Python suite adds:
- Legacy database migration when both `chain_tip` and `chain_tip_version` are absent; verifies the reconstructed anchor matches the replayed chain and that version 1 is written.
- Rejection of malformed CBOR bytes in either `chain_tip` or `chain_tip_version`.

All four workflows passed on that exact commit:
- HND Python tests run `42401168591`: PASS.
- CometBFT one-node smoke run `42401168559`: PASS.
- CometBFT three-validator smoke run `42401168669`: PASS.
- CometBFT four-validator liveness/recovery run `42401168614`: PASS.

The metadata anchor and version marker are stored in the same SQLite database. Deletion or coordinated replacement of both markers cannot be detected by this in-database mechanism alone; an independently stored checkpoint or signed external backup is required for that threat model.

## Runtime chain-tip integrity guard

On code/test commit `86dc2e53bb1a0a7a9348c03336f7e22aff5950b7`, the chain now validates the persisted `chain_tip_version` and `chain_tip` anchor against the in-memory height and tip hash before accepting an append. The metadata update during block persistence must affect exactly one row; otherwise the append fails and the SQLite transaction rolls back.

Two regression tests remove the tip anchor or version marker through a second SQLite connection while the chain process remains open. In both cases, append fails closed and the chain height/block state does not advance.

All four workflows passed on this exact code commit:
- HND Python tests run `42401439072`: PASS.
- CometBFT one-node smoke run `42401439028`: PASS.
- CometBFT three-validator smoke run `42401439056`: PASS.
- CometBFT four-validator liveness/recovery run `42401439030`: PASS.

These are targeted in-process metadata-tampering regressions plus the listed CI integration paths. They do not protect against coordinated deletion or replacement of both metadata markers in the same SQLite database; an independently stored checkpoint remains necessary for that threat model.

## External rollback protection — design only

The design and trust boundary are recorded in `docs/ROLLBACK_PROTECTION_DESIGN.md`. An older internally consistent SQLite snapshot can still pass the current in-database chain-tip checks. A local sidecar or key stored beside SQLite is not an independent anti-rollback authority. The proposed strict design requires an independently administered monotonic checkpoint authority, binds chain ID/genesis hash/height/block hash/state commitment/sequence, and fails closed across the SQLite-to-authority crash window. Required adversarial cases are listed in the design document. No provider or key custody has been configured; external rollback protection remains NOT IMPLEMENTED and NOT VERIFIED.

All four workflows passed on code commit `166231c251dbcb181e52dd65af0cdda191f3fb64`: Python `42401814429`, one-node `42401814447`, three-validator `42401814426`, four-validator `42401814441`.


## Signed rollback checkpoint primitives — exact-commit evidence

Code commit `be1e5725707861b7996ea6b1bfeb2b939653a127` adds canonical checkpoint records, Ed25519 signatures verified against a pinned public key, strict payload/envelope decoding, successor monotonicity checks, and a volatile in-memory authority test double with compare-and-swap and concurrent-update coverage.

All four workflows passed on this exact commit:
- HND Python tests: run `42402800672`, PASS.
- One-node CometBFT restart: run `42402800686`, PASS.
- Three-validator integration: run `42402800837`, PASS.
- Four-validator liveness/recovery: run `42402800633`, PASS.

Scope limitation: these tests verify record/signature primitives and an in-memory test authority only. They do not verify durable remote CAS, independent key custody, startup enforcement, DB/checkpoint crash-window recovery, authority outages, or production anti-rollback protection.


## Checkpoint reconciliation assessment

Added a pure fail-closed assessment for local tip versus trusted checkpoint. Tests cover unanchored, exact match, local behind, local ahead requiring explicit suffix verification, divergent commitments, wrong chain/genesis, and boolean height rejection. The assessment is not yet integrated into startup or commit paths and does not independently prove suffix ancestry.


## Checkpoint ancestry checks for local-ahead databases

The local-tip assessment accepts the replayed local block hash and app hash at the trusted checkpoint height. A mismatch is rejected as divergence; a match still leaves the suffix in recovery-required status. Tests cover both commitment mismatches and missing/partial ancestry evidence. No writes are enabled merely because the checkpoint is an ancestor.


## LocalChain-to-checkpoint assessment integration

Added a cross-module regression test that creates a signed checkpoint at an earlier local height, advances the local chain, retrieves the replay-verified ancestor commitments from `LocalChain.checkpoint_ancestor_commitments`, and feeds them to `assess_local_tip`. The expected result remains local-ahead/recovery-required with writes disabled.


## Idempotent checkpoint acknowledgement retry

Added tests proving that an exact signed checkpoint retry after a simulated lost acknowledgement succeeds without creating another sequence, while a different candidate with the stale expected sequence/digest is rejected. These tests run against the volatile in-memory authority test double and do not prove remote durability.


## Authenticated authority read and fail-closed assessment

Tests cover a valid pinned-key checkpoint, missing record, untrusted signature, authority outage, and invalid response type. The read/verify/assess helper is a composition layer only and is not wired into node startup or write admission.


## Provider-neutral checkpoint publication helper

Tests cover first publication, monotonic successor publication, exact retry, skipped sequence rejection, CAS conflict, and authority outage. The helper verifies the signed candidate and current authority state before CAS, then rereads to resolve an ambiguous false CAS result. It does not close the SQLite/remote distributed-commit crash window and is not integrated into the live consensus commit path.


Additional test: simulated authority durably stores a candidate but returns false from CAS; publisher rereads and resolves the exact stored candidate as success without creating another sequence.


## LocalChain authority assessment integration

Added end-to-end unit tests for `assess_local_chain`: exact genesis match, local-behind, local-ahead with matching ancestry (writes remain disabled), and divergent ancestor rejection. This helper combines LocalChain replay commitments with authenticated authority reads, but it is not wired into the running CometBFT startup or commit lifecycle.


## Local-tip-bound checkpoint publication

Added `publish_local_chain_checkpoint` on the implementation branch. It verifies the signed checkpoint against the replay-verified local chain's exact chain ID, genesis hash, height, block hash, and application-state commitment before delegating to provider-neutral CAS publication. Tests reject wrong height, block hash, application hash, and an untrusted signer. This helper does not establish consensus finality or atomicity with SQLite and is not wired into ABCI commit. Production external authority remains unconfigured.
