# WP4.14 Token Supply, Balance and Transfer Invariants Audit — 2026-11-05

## Scope and method

Static source and test review of the `phase-0.2-planning` branch at commit `d7d596b60677c48f8cbbcfe4d5a8068725537e8b`. Reviewed:

- `hnd_v02/genesis.py`
- `hnd_v02/transaction.py`
- `hnd_v02/ledger.py`
- `hnd_v02/abci_app.py`
- `tests/test_v02_genesis_manifest.py`
- `tests/test_v02_transaction_envelope.py`
- `tests/test_v02_ledger.py`
- `tests/test_v02_four_replica_state_convergence.py`
- `vectors/v0.2-genesis-devnet-example.json`

This is a code-and-test-traceability audit, not a monetary-policy approval, production security certification, or independent execution of every test in this review.

## Executive result

**NOT APPROVED as proof of a fixed public one-million-HND monetary policy or production issuance controls.** The reviewed local v0.2 reference ledger has useful transfer and accounting invariants, but the one-million value is not a protocol-wide constant. It is a value declared by a Genesis manifest and authenticated only if the expected Genesis hash is itself distributed and pinned through a trusted process.

## Positive controls observed

1. **Genesis allocation arithmetic:** `validate_genesis_manifest` requires a positive integer `total_supply`, positive integer allocation amounts, strictly increasing unique account IDs, valid key-to-account derivation, and exact equality between the sum of allocations and declared supply.
2. **Genesis identity:** the manifest hash is domain-separated and compared with `expected_genesis_hash`. The module itself warns that a hash supplied alongside an untrusted manifest does not authenticate its origin.
3. **No implicit mint/burn operation:** the reviewed `HNDLedger` exposes transfer application and account views; no mint, burn, fee, reward, or issuance transition was found in this ledger implementation. A transfer changes two balances by equal and opposite amounts.
4. **Transfer validation:** transactions require a positive integer amount no greater than `config.max_amount`, a valid sender balance, an existing sender and recipient, a valid signature, matching network/protocol, and the exact expected nonce. Self-transfers are rejected.
5. **Replay and nonce controls:** accepted transaction IDs are tracked; duplicate transactions and stale nonces are rejected. Nonces are constrained to unsigned 64-bit range and exhaustion is rejected before mutation.
6. **Accounting invariant:** after each applied transaction, the ledger asserts that all balances are non-negative integers and their sum equals `total_supply`. Python integers avoid fixed-width arithmetic wraparound in the balance addition/subtraction path.
7. **Deterministic state commitment:** balances and nonces are key-sorted, accepted IDs are sorted, and canonical JSON is hashed with a state domain prefix. The state payload commits to total supply, balances, nonces, accepted transaction IDs, and history.
8. **Recovery integrity:** snapshots are reconstructed by replaying signed history from Genesis; stored balances and state hash are compared with the rebuilt state.
9. **Test evidence in repository:** tests cover genesis allocation-sum and type failures, malformed/self transfers, overspend rejection without state change, duplicate/stale-nonce rejection, stable supply through 2,000 alternating signed transfers, and four-replica equal-input app-hash convergence plus divergence detection.

## Findings and boundaries

### F1 — One million HND is not hard-coded as a protocol invariant

**Severity: High for a claim of fixed public supply; conditional on deployment configuration.**

The Genesis validator accepts any positive integer `total_supply` if the allocations sum to it and the supplied expected hash matches. The sample vector declares 1,000,000, but its description explicitly identifies it as test-only devnet data, not an approved public distribution. The tests also construct manifests with one million as fixture data. No immutable protocol constant or mandatory public-network supply value was found in the reviewed files.

**Impact:** a different valid manifest and corresponding trusted expected hash can define a different supply. Therefore the code proves internal consistency of a pinned Genesis, not that the public network must have exactly 1,000,000 HND.

**Required before public launch:** approve the monetary policy and distribution; publish the canonical production Genesis; pin its hash in a separately trusted release/configuration process; ensure every validator is forced to use the same authenticated hash and configuration.

### F2 — `max_amount` is externally supplied and not bound to Genesis

**Severity: High for cross-validator configuration safety.**

`ProtocolConfig.max_amount` is a caller-supplied positive integer. It is not a field in the Genesis manifest and is not included in the manifest hash. The transfer validator uses it as the per-transaction ceiling.

**Impact:** validators started with different `max_amount` values can disagree on whether a transaction is valid, even while using the same Genesis manifest. This is a consensus-critical configuration binding gap, not an arithmetic overflow.

**Required:** bind all consensus-critical monetary parameters to a canonical, authenticated application configuration/Genesis identity, and reject startup if local values differ. Do not treat a CLI-provided value as an independently trusted monetary policy.

### F3 — No production mint/burn/fee/reward policy or transition is implemented

**Severity: Medium / design boundary, not a defect if intentionally out of scope.**

No mint, burn, fee collection, validator reward, or supply-adjustment API was found in the reviewed ledger. The current transfer-only model preserves the Genesis supply. This is a positive restriction for the present prototype, but it is not evidence of a complete future monetary policy.

**Required:** explicitly decide whether supply is permanently fixed. If future issuance, burn, fees, or rewards are desired, specify authorized actors, limits, accounting destinations, event ordering, replay semantics, and consensus-critical validation before implementation. No such operation should be added as an administrative or off-chain balance edit.

### F4 — Balance integers have no explicit monetary upper bound

**Severity: Medium; mitigated by current supply-conservation invariant when state is valid.**

Python integers do not wrap at 64 bits. The code rejects negative balances and checks that the balance sum equals the manifest supply. However, Genesis `total_supply` and allocation amounts have no explicit upper bound, and recipient balance growth has no explicit per-account maximum.

**Impact:** this is not a demonstrated wraparound vulnerability in the current Python implementation. It leaves the monetary unit/range policy unbounded and may create interoperability risks for future protobuf, database, wallet, or client implementations with fixed-width numeric types.

**Required:** define a protocol-wide maximum supply and account-balance representation/range before interoperability work; validate Genesis and all state values against it. Ensure all clients encode the same integer range.

### F5 — App-hash convergence is demonstrated for a synthetic four-replica test, not full network consensus

**Severity: Medium / evidence boundary.**

The four-replica test instantiates four local ABCI application objects with identical Genesis and inputs, checks equal app hashes and committed fingerprints, then deliberately creates a same-height divergent transition and detects the mismatch. The test module explicitly says it is an application-layer test, not a consensus or Byzantine-fault proof.

**Impact:** useful evidence of deterministic application replay for that test path, but it does not establish all production validators use the same authenticated configuration, binary, Genesis, or CometBFT consensus execution under adversarial conditions.

**Required:** retain this test and add deployment-level checks that compare authenticated configuration/Genesis identity and application hashes across independently provisioned validators.

## Test and CI traceability

Repository tests inspected (source review): Genesis manifest, transaction envelope, ledger, and four-replica convergence tests. Their source includes the cases summarized above. This audit did not independently execute the Python test commands.

GitHub Actions run `41983052863` is recorded as **completed / success** for the exact reviewed head commit `d7d596b60677c48f8cbbcfe4d5a8068725537e8b`. Its `hnd-v02-tests` and `cometbft-single-node-smoke` jobs both completed successfully; the first job's `Run isolated v0.2 tests` step completed successfully. This is CI evidence for the workflow as configured, not proof that every possible monetary boundary or production deployment scenario was tested.

Not demonstrated by this audit:
- exhaustive fuzz/property testing of arbitrary Genesis supply and allocation sizes;
- fixed-supply enforcement for a production network;
- cross-validator rejection of mismatched `max_amount` configurations;
- production issuance/burn/fee/reward governance (none is implemented here);
- fixed-width interoperability limits across wallets, protobufs, databases, and external APIs;
- Byzantine consensus or production deployment correctness.

## Disposition

- Transfer accounting invariants in the reviewed local ledger: **PASS by source inspection and existing test coverage**.
- Genesis allocation sum and pinned-manifest comparison: **PASS as implemented**, subject to trusted distribution of the expected hash.
- Fixed public supply of exactly 1,000,000 HND: **NOT ESTABLISHED**.
- Consensus-critical monetary configuration binding: **GAP**.
- Mint/burn/reward policy: **NOT IMPLEMENTED / POLICY DECISION REQUIRED**.
- Production readiness: **NOT APPROVED by this audit**.

No source code, tests, or workflow files were modified for this review.
