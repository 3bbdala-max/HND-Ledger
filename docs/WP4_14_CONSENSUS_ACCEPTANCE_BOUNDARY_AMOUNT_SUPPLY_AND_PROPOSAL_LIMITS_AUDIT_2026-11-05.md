# WP4.14 — Consensus Acceptance Boundary Audit: Amount, Supply, and Proposal Limits

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Baseline head:** `ed60036fa24f3ae17f3ed02291fd1eb2659e152f`  
**Status:** Static source audit only; no code/test changes; no tests run.

## 1. Executive finding

The current v0.2 implementation has deterministic local validation primitives, but several acceptance limits are not committed to a shared network identity. This is a consensus-configuration gap, not evidence that a live network has diverged.

## 2. Confirmed source behavior

### 2.1 Per-transaction amount

- `ProtocolConfig.max_amount` must be a positive Python integer, with no upper bound.
- `validate_transaction` rejects a transfer when `amount > config.max_amount`.
- The CometBFT server CLI supplies this value independently through required `--max-amount`.
- The legacy Genesis manifest hash commits to the manifest only; it does not commit to `max_amount`.

**Consequence:** two nodes started with different CLI values can apply different transaction-validity rules while presenting the same legacy manifest hash.

### 2.2 Total supply and arithmetic

- Genesis validation requires positive integer `total_supply` and positive integer allocation amounts whose sum equals `total_supply`.
- No explicit protocol-wide upper bound is enforced for total supply or allocation amounts.
- Python integer arithmetic is exact and unbounded, so the current Python implementation does not wrap on addition.
- That does not define portable consensus behavior for another implementation language with fixed-width integers.
- Ledger invariants check that the sum of balances remains equal to the Genesis total supply after transfers.

**Consequence:** conservation is checked, but the numeric domain is not yet a frozen cross-language protocol contract.

### 2.3 Proposal transaction count and bytes

- `MAX_BLOCK_TRANSACTIONS = 1000` is a source-level constant used by the shared transaction-list validator.
- `PrepareProposal` uses the byte budget supplied by the CometBFT request to select transactions.
- `ProcessProposal` checks transaction count and transaction validity, but does not independently apply a configured aggregate byte ceiling.
- The CometBFT engine has its own block-size configuration; the reviewed HND source does not bind a complete resolved CometBFT profile to the HND application identity.

**Consequence:** the HND-level count rule is explicit in code, but the full count/byte acceptance envelope is not yet represented in one verified, versioned network configuration.

## 3. Risk classification

| Finding | Risk | Required treatment |
|---|---|---|
| Node-local `--max-amount` | Consensus divergence | Bind to verified Config-v1 identity; reject CLI mismatch |
| No portable `amount_max` | Cross-language overflow/precision divergence | Freeze bounded integer semantics and vectors |
| No total-supply ceiling | Cross-language range mismatch | Define supply and allocation maxima |
| Hard-coded 1000 transaction count | Unversioned protocol rule | Move into frozen config or explicitly freeze as protocol constant |
| Proposal byte budget not independently bound by HND config | Different resource/acceptance envelope | Freeze HND and CometBFT limits and test cross-node mismatch |

## 4. Required decisions before implementation

1. Freeze `amount_max`, `max_amount`, and their relationship.
2. Freeze `total_supply_max` and allocation arithmetic semantics.
3. Decide whether the 1000-transaction ceiling remains a protocol constant or becomes a Config-v1 field.
4. Freeze maximum transaction bytes and maximum block bytes, distinguishing HND application policy from CometBFT engine policy.
5. Specify exact integer encoding and cross-language overflow rejection.
6. Include every consensus-critical value in the appropriate Config-v1 or CometBFT profile identity.
7. Require startup to compare command-line operational arguments against the pinned values before opening the ABCI listener.

Do not choose numeric ceilings by guesswork. Measure existing fixtures and representative workloads, inspect CometBFT constraints, and then freeze values with boundary and cross-language test vectors.

## 5. Minimum acceptance tests

- Amount at 1, `max_amount`, and `max_amount + 1`.
- `max_amount` at and above `amount_max`.
- Total supply at the selected maximum and one unit above.
- Allocation sum exact, one unit below, and one unit above.
- Large integer vectors across Python and an independent implementation.
- Same Genesis with mismatched `--max-amount` must fail startup once Config-v1 is implemented.
- Proposal at transaction-count limit and one over.
- Proposal at byte limit and one over.
- Deliberate HND/CometBFT profile mismatch must fail preflight.
- All validators given the same pinned profile must produce identical proposal acceptance.

## 6. Scope and status

This audit does not alter token supply, issuance, transfer semantics, Genesis hash, transaction encoding, or CometBFT settings. It does not establish that the current draft is production-ready.

**Disposition:** retain the existing v0.2 implementation as a draft/test profile. Do not label its amount or resource limits production-frozen. Resolve these items through the already documented Config-v1 decision and change-gate process before implementing or launching a public network.
