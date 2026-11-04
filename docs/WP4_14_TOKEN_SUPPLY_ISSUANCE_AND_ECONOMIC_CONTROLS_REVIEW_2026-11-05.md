# HND v0.2 — Token supply, issuance, and economic-control review

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Static economic and monetary-safety review  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation-only review of the current reference implementation. No code or workflow files changed.

## 1. Executive result

The inspected v0.2 code implements a **Genesis-funded, transfer-only ledger reference**. It has no transaction or ABCI operation that mints, issues, burns, rewards, charges fees, or changes the account registry after initialization. Accepted transfers conserve the Genesis-declared total supply.

The familiar **1,000,000 HND** figure is present in a two-account devnet fixture and test fixtures only. The accompanying Genesis document explicitly says this is synthetic test data, not an approved public supply, distribution, or issuance commitment. No public tokenomics decision is established by this code.

## 2. Source reviewed

The review inspected the current branch versions of:

- `hnd_v02/genesis.py`
- `hnd_v02/transaction.py`
- `hnd_v02/ledger.py`
- `hnd_v02/abci_app.py`
- `tests/test_v02_genesis_manifest.py`
- `tests/test_v02_ledger.py`
- `tests/test_v02_transaction_envelope.py`
- `tests/test_v02_abci_app.py`
- `vectors/v0.2-genesis-devnet-example.json`
- `docs/WP1_V02_GENESIS_MANIFEST_2026-10-31.md`
- `docs/WP2_V02_LEDGER_REFERENCE_2026-10-31.md`

This was source and test inspection. No test command was executed as part of this review.

## 3. What the implementation currently enforces

### 3.1 Genesis supply and allocation

- The manifest requires a positive integer `total_supply` and a non-empty allocation list.
- Each allocation must contain exactly `account_id`, `public_key`, and a positive integer `amount`.
- Allocation entries must be sorted and unique; each account ID must derive from its declared public key.
- The validator sums all allocation amounts and rejects the manifest unless the sum exactly equals `total_supply`.
- The caller must supply an independently trusted expected Genesis hash. A hash distributed alongside an untrusted manifest is not sufficient authentication.
- The example fixture declares 1,000,000 units, allocated 600,000 / 400,000 to two synthetic test accounts.

**Interpretation:** the code validates a proposed initial distribution against a pinned hash. It does not decide who is entitled to receive units, authorize the publisher of the hash, or implement a public distribution ceremony.

### 3.2 Transfers and supply conservation

- A transaction has a fixed schema: protocol version, network ID, sender, recipient, amount, nonce, and signature.
- The amount must be an exact positive integer, no greater than the configured `ProtocolConfig.max_amount`, and no greater than the sender's available balance.
- Self-transfers, unknown accounts, malformed account IDs, wrong network/version, invalid signatures, stale nonces, and duplicate transaction IDs are rejected.
- The ledger computes the candidate balances before mutation and checks that the resulting sum remains exactly equal to the original `total_supply`.
- The ledger invariant also requires all balances to be non-negative and the account, public-key, and nonce registries to match.
- Snapshot recovery reconstructs state from Genesis and signed transaction history instead of trusting serialized balances.

**Interpretation:** within this reference model, a user cannot create value merely by submitting a transfer with an arbitrary amount. The recipient must already exist in the Genesis account registry.

### 3.3 Issuance, burning, fees, rewards, and administration

The reviewed transaction schema and ABCI application expose no mint, issue, burn, fee, staking-reward, validator-reward, treasury, or administrator transaction path. The ledger has no post-Genesis account-creation operation. The Genesis validator rejects unknown manifest fields, and its tests include rejection of an added `mint` field.

There is no implemented inflation schedule, emission schedule, fee sink, burn policy, treasury policy, staking economics, or governance authorization for monetary changes.

**Interpretation:** no ongoing issuance mechanism was found in the reviewed v0.2 path. This is a property of the inspected implementation, not a permanent guarantee against future code changes, malicious software releases, or replacement of the trusted Genesis/configuration.

## 4. Gaps and unresolved economic decisions

| ID | Gap | Required decision or control |
|---|---|---|
| ECON01 | One million is a test fixture, not an approved supply. | Decide whether supply is fixed, capped, or inflationary before any public launch. |
| ECON02 | Atomic-unit meaning and decimal display precision are unspecified. | Define integer base units, display decimals, rounding, and wallet/API representation. |
| ECON03 | No protocol-wide maximum supply or cross-language numeric bound is specified. | Set an explicit supply ceiling and portable integer bounds; test overflow behavior in every implementation. |
| ECON04 | `max_amount` is a local protocol configuration parameter, not a global monetary cap. | Define its consensus-critical value, authenticated distribution, and upgrade rules. |
| ECON05 | No issuance/burn operation exists. | If future issuance or burn is desired, specify an explicit state transition, authority, limits, event history, and deterministic tests. Otherwise explicitly freeze these operations out of scope. |
| ECON06 | No monetary governance or authorized Genesis publisher process is implemented. | Define who can approve and authenticate Genesis and any future monetary parameter change. |
| ECON07 | No fee, validator reward, staking, treasury, or incentive model exists. | Decide whether these are intentionally absent; do not imply validators are economically rewarded by the current code. |
| ECON08 | No account creation after Genesis. | Decide whether new accounts must be preallocated at Genesis or whether a separately specified account-registration mechanism is required. |
| ECON09 | No formal supply-conservation property suite across all state transitions and independent implementations. | Add property-based, adversarial, cross-language, restart, and multi-node supply-invariant tests before release. |
| ECON10 | A pinned hash authenticates content only when the pin itself is trusted. | Establish signed release manifests, publisher-key custody/rotation, and independent pin distribution. |

## 5. Recommended safe design boundary

Until a separate economic specification is reviewed and approved:

1. Treat the current ledger as **fixed-at-Genesis and transfer-only**.
2. Keep mint, burn, fees, rewards, staking, treasury, and monetary governance unimplemented.
3. Treat 1,000,000 only as a devnet test parameter; do not describe it as the final supply.
4. Do not publish allocation recipients or percentages based on the two-account fixture.
5. Define base-unit precision, maximum supply, integer bounds, and configuration pinning before a cross-language implementation is accepted.
6. Require an authenticated, independently reviewed Genesis release process before any public network or asset distribution.

## 6. Test evidence and limits

The inspected tests contain cases for exact Genesis allocation sums, malformed and non-integer supply/allocation values, duplicate or unordered allocations, account/public-key mismatch, overspending, invalid amounts, nonce and replay rejection, and supply preservation over a 2,000-transfer test scenario. The ABCI tests exercise transaction admission, proposal/finalization, and committed-state recovery.

These are **test definitions observed in source**, not tests executed during this review. Historical CI evidence described in earlier project records must not be mistaken for a fresh run of these tests at the current branch head. No new runtime, integration, property-based, or independent implementation test was run for this report.

## 7. Release and safety status

- This review did not change application code or CI workflows.
- No real tokens, funds, keys, or public network were used.
- No public supply, distribution, monetary policy, or legal status is approved.
- Production, public distribution, and release gates remain **CLOSED**.
