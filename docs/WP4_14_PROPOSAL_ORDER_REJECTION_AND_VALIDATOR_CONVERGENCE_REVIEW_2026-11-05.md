# HND v0.2 — Proposal ordering, rejection, and validator state-convergence review

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Deterministic block input and validator convergence  
**Branch:** `phase-0.2-planning`  
**Reviewed head:** `744f841d5f4afcfd1a512d33338b724f8cebdba5`  
**Status:** Documentation-only static review. No source, test, or workflow files changed.

## 1. Executive result

The ABCI application processes transaction lists in the exact order supplied by CometBFT. It does not sort transactions locally. This is appropriate for a consensus state machine: the decided block's ordered transaction bytes are the common deterministic input, and every honest validator must execute that same sequence under identical protocol configuration.

The review confirms three distinct behaviors that must remain explicit:

1. **PrepareProposal** greedily scans the proposer-provided transaction list in order, selecting transactions that fit the byte budget and are valid against the evolving candidate ledger. Invalid or over-budget transactions are skipped; later transactions are still considered.
2. **ProcessProposal** validates the exact proposed ordered list against a clone of committed state. One invalid transaction causes the whole proposal to be rejected. The committed state is not mutated.
3. **FinalizeBlock** executes the decided ordered list transaction by transaction. An invalid transaction receives a failed result, does not mutate candidate state, and does not prevent later transactions from being evaluated. The resulting candidate ledger is committed only through Commit.

These behaviors are not inherently contradictory: proposal admission and execution have different contracts. However, tests must prove that every validator receiving the same decided block produces identical per-transaction results and app hash, including invalid entries and conflicting nonce sequences.

## 2. Source behavior observed

### 2.1 PrepareProposal is order-sensitive by design

The proposer method:
- clones committed state, not the local mempool ledger;
- iterates the supplied transaction list in order;
- skips a transaction if adding its bytes would exceed `max_tx_bytes`;
- attempts each remaining transaction against a trial clone of the current candidate;
- skips transactions that fail decoding or ledger validation;
- advances the candidate only when a transaction succeeds;
- returns the selected bytes in their original relative order.

It does not sort by sender, nonce, fee, transaction ID, or arrival timestamp. Consequently, changing the input order can change which transactions are selected, particularly when they conflict on sender nonce/balance or compete for a finite byte budget. That is proposer selection behavior; once a block is proposed/decided, the exact ordered list is the deterministic application input.

### 2.2 ProcessProposal validates the entire ordered proposal

The validator clones committed state and applies each proposed transaction sequentially. If any transaction fails, the method returns REJECT through the CometBFT adapter. It does not publish or persist candidate state.

For two distinct transactions using the same sender nonce, the first may validate against the committed state while the second fails. Reversing their order may change which transaction is the valid first spend. Both validators must receive and evaluate the same order for a consistent decision.

### 2.3 FinalizeBlock records per-transaction failures and continues

FinalizeBlock also starts from committed state and processes transactions sequentially, but it isolates each transaction using a trial ledger:
- success replaces the candidate with the trial state;
- failure appends a non-zero result and leaves candidate unchanged;
- later transactions are still evaluated against the last successful candidate;
- the app hash is calculated from the resulting candidate state and evidence journal.

This means a block containing an invalid transaction can yield a failed result for that transaction while later valid transactions still execute. This is different from ProcessProposal's whole-proposal rejection rule.

### 2.4 Configuration identity remains a consensus prerequisite

The application uses a process-supplied `ProtocolConfig`, including `max_amount`. The reviewed code validates network ID and protocol version against Genesis/chain identity, but `max_amount` is not committed in the Genesis manifest/hash or ABCI Genesis payload. Different validator values can therefore produce different transaction validity decisions for the same ordered block.

This is a known, previously documented consensus-critical configuration gap (see the existing transfer concurrency/arithmetic review). It remains a release blocker until the parameter is bound to an authenticated versioned protocol configuration or startup independently rejects a mismatch.

## 3. Existing tests found

The inspected ABCI test suite includes:
- PrepareProposal selects a sequential valid subset and skips invalid entries;
- PrepareProposal respects byte limit and validates budget/list types;
- ProcessProposal accepts a valid sequential sequence without mutating committed state;
- ProcessProposal rejects conflicting nonce transactions;
- ProcessProposal rejects invalid signatures without state mutation;
- FinalizeBlock records invalid transaction results and continues with valid transactions;
- invalid execution does not partially mutate the candidate;
- distinct ProcessProposal calls do not leak candidate state;
- a four-replica test sends identical block inputs to independent applications and compares resulting state.

These are test definitions inspected in the repository. No test command was executed during this review.

## 4. Risks and boundaries

| ID | Severity | Finding | Required evidence/control |
|---|---|---|---|
| ORD01 | High | Different transaction ordering can select different winners for conflicting sender nonces or balances. | Prove all validators execute the exact committed order; add permutation tests that document expected order-sensitive outcomes. |
| ORD02 | High | ProcessProposal rejects the whole proposal on one invalid transaction, while FinalizeBlock emits a failed result and continues. | Pin CometBFT v0.40.0 behavior and test the full proposal/vote/finalize path; document whether and under what conditions a locally rejected proposal can ever be finalized. |
| ORD03 | High | Different `max_amount` values across validators can produce different accept/reject outcomes and app hashes. | Bind `max_amount` to canonical Genesis/config identity before multi-validator release. |
| ORD04 | Medium | PrepareProposal's greedy selection depends on incoming order and byte budget; it is not a globally optimal packing or canonical transaction sort. | Treat proposer selection as policy, not consensus truth; test deterministic behavior for fixed ordered inputs and budgets. |
| ORD05 | Medium | The four-ABCI replica test uses identical inputs; it does not by itself establish CometBFT's real multi-node proposal rejection/voting behavior. | Add a pinned four-node CometBFT integration scenario with conflicting transactions, invalid signatures, and proposal rejection. |
| ORD06 | Medium | Existing unit tests do not establish that every per-transaction result, event, evidence journal, and app hash is identical across all four replicas for a block containing invalid entries. | Compare full ordered result vectors and committed snapshots/app hashes across all four nodes. |

## 5. Required acceptance matrix

These tests are proposed, not executed:

| ID | Scenario | Required outcome |
|---|---|---|
| ORD-T01 | Same two conflicting transactions, order A then B, in PrepareProposal | Deterministic selected subset for fixed input and byte budget |
| ORD-T02 | Reverse the same conflicting transactions | Outcome may differ by order, but must be deterministic and documented |
| ORD-T03 | Same exact ordered proposal sent to four independent apps | Identical ProcessProposal status |
| ORD-T04 | Same exact ordered decided block with one invalid transaction sent to four apps | Identical ordered result codes/log classes, committed ledger, evidence journal, and app hash |
| ORD-T05 | Valid nonce N, invalid conflicting nonce N, then valid nonce N+1 | Failed middle transaction leaves candidate unchanged; later N+1 may succeed if otherwise valid |
| ORD-T06 | Invalid transaction first, then valid nonce N | Invalid first entry does not consume nonce; valid N succeeds |
| ORD-T07 | One node has a different `max_amount` | Startup must fail after configuration is bound to canonical network identity; never allow silent consensus divergence |
| ORD-T08 | Same block under different byte budgets at proposal preparation | Proposer may select different candidate blocks; any actually decided block must converge identically |
| ORD-T09 | Real CometBFT four-node proposal with one validator returning REJECT | Capture vote behavior, decision outcome, and whether FinalizeBlock is invoked on every node |
| ORD-T10 | Restart all nodes after the same mixed-success block | Restored heights, app hashes, balances, nonces, and accepted transaction IDs remain identical |

## 6. Recommended execution order

1. Resolve the already-known `max_amount` consensus configuration gap.
2. Add the full four-replica mixed-success result-vector comparison (ORD-T04–T06).
3. Run a pinned CometBFT v0.40.0 four-node integration for ProcessProposal rejection and subsequent FinalizeBlock behavior (ORD-T09).
4. Record exact node configuration, software version, ordered block bytes, votes, transaction results, committed hashes, and restart comparisons.
5. Keep proposer ordering policy separate from deterministic execution rules; do not add local sorting during validation or finalization.

## 7. Release conclusion

The HND application is order-preserving and its state transition logic is deterministic for the same ordered block bytes, same committed starting state, and same protocol configuration. The existing code and unit tests provide meaningful evidence for this narrow claim.

They do **not** establish full four-validator convergence under heterogeneous configuration or the complete CometBFT proposal-rejection path. The `max_amount` mismatch remains a material consensus risk and must be closed before production consensus claims.

No source, tests, or workflows were modified. No tests or CometBFT network runs were executed for this report.
