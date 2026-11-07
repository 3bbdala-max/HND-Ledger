# HND consensus test matrix

Status: limited local CometBFT integration subset passed. Adversarial consensus matrix remains incomplete.

## Executed subset

| ID | Scenario | Evidence | Result |
|---|---|---|---|
| C-01a | Three local validators reach a common height and agree on post-transfer app hash | Run 42360867085 | PASS |
| C-01b | Valid signed transfer committed exactly once on each ledger | Run 42360867085 | PASS |
| C-01c | Restarted validator retains transfer, balances, nonce, and app hash | Run 42360867085 | PASS |
| C-01d | Account and ledger-info RPC queries return committed state on all nodes | Run 42360867085 | PASS |
| C-01e | Signed overspend admitted by weak CheckTx but excluded by PrepareProposal | Run 42360867085 | PASS |
| C-02a | One-node CometBFT restart and continued block production | Run 42360867084 | PASS |
| C-12 | Wrong chain ID and conflicting genesis retry rejected | Python tests, run 42360867069 | PASS |
| C-14 | Malformed and oversized IPC frames rejected | Python/Go tests | PASS |
| C-15 | Deterministic state replay and commitment agreement | Runs 42360867084 and 42360867085 | PASS |

The three validators used separate processes and data directories but ran on one CI runner. This is not an independent multi-host or multi-operator test.

## Not yet executed

| ID | Scenario | Required invariant |
|---|---|---|
| C-02 | Conflicting proposals at same height/round | No conflicting finalization by honest validators |
| C-03 | Duplicate vote | No additional voting power |
| C-04 | Replay vote from old height | Message rejected |
| C-05 | Vote from wrong chain ID | Message rejected |
| C-06 | Byzantine voting power below one-third | Safety maintained within protocol fault assumptions |
| C-07 | Byzantine voting power at or above one-third | No unsupported safety/liveness guarantee claimed |
| C-08 | Network partition | No conflicting finalization; liveness may pause |
| C-09 | Partition heals | Nodes converge under selected protocol |
| C-10 | Validator crashes after signing | Restart cannot produce conflicting signature |
| C-11 | Validator-set update | Old/new set boundary follows protocol rules |
| C-13 | State sync from trusted checkpoint | Replayed state commitment matches checkpoint |
| C-16 | Sustained adversarial mempool load | Bounded resource use and deterministic rejection |

## Evidence required

Each adversarial run must record CometBFT version, source commit, genesis hash, validator-set hash, node identities, voting power, scenario configuration, logs, finalized height, block hash, and application state commitment. Reports must distinguish passed, failed, skipped, timed out, pending, and not run.
