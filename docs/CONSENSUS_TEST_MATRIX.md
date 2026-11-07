# HND consensus test matrix

Status: local CometBFT integration subset passed, including a live four-validator network-partition and healing scenario on one CI runner. The broader adversarial consensus matrix remains incomplete.

## Executed subset

| ID | Scenario | Evidence | Result |
|---|---|---|---|
| C-01a | Three local validators reach a common height and agree on post-transfer app hash | Run 42360867085 | PASS |
| C-01b | Valid signed transfer committed exactly once on each ledger | Run 42360867085 | PASS |
| C-01c | Restarted validator retains transfer, balances, nonce, and app hash | Run 42360867085 | PASS |
| C-01d | Account and ledger-info RPC queries return committed state on all nodes | Run 42360867085 | PASS |
| C-01e | Signed overspend admitted by weak CheckTx but excluded by PrepareProposal | Run 42360867085 | PASS |
| C-02a | One-node CometBFT restart and continued block production | Run 42360867084 | PASS |
| C-08 | Live network partition: validator 0 remains running but isolated; validators 1–3 retain quorum and advance | Commit `747560b396344d89d3fb223fe12ee29c95684a0c`, run `42377936382`; validator 0 peers=0, validators 1–3 peers=2 each; heights 7 vs 12 | PASS (single CI host) |
| C-09 | Heal partition; isolated validator catches up and all four app hashes converge | Same commit/run; all four agree at height 12, app hash `2FA595F9328078EB77A6EE62BDAD3743D619B1371BB82DD78AD0D98FAECC03A9` | PASS (single CI host) |
| C-12 | Wrong chain ID and conflicting genesis retry rejected | Python tests, run 42360867069 | PASS |
| C-14 | Malformed and oversized IPC frames rejected | Python/Go tests | PASS |
| C-15 | Deterministic state replay and commitment agreement | Runs 42360867084 and 42360867085 | PASS |

The three-validator test used separate processes and data directories on one CI runner. The four-validator partition test also used four separate processes/data directories on one CI runner: validator 0 was kept alive but isolated at height 7 while validators 1–3 advanced to height 12; after healing, validator 0 caught up and all four app hashes matched. Neither test is an independent multi-host or multi-operator test.

## Not yet executed

| ID | Scenario | Required invariant |
|---|---|---|
| C-02 | Conflicting proposals at same height/round | No conflicting finalization by honest validators |
| C-03 | Duplicate vote | No additional voting power |
| C-04 | Replay vote from old height | Message rejected |
| C-05 | Vote from wrong chain ID | Message rejected |
| C-06 | Byzantine voting power below one-third | Safety maintained within protocol fault assumptions |
| C-07 | Byzantine voting power at or above one-third | No unsupported safety/liveness guarantee claimed |
| C-10 | Validator crashes after signing | Restart cannot produce conflicting signature |
| C-11 | Validator-set update | Old/new set boundary follows protocol rules |
| C-13 | State sync from trusted checkpoint | Replayed state commitment matches checkpoint |
| C-16 | Sustained adversarial mempool load | Bounded resource use and deterministic rejection |

## Evidence required

Each adversarial run must record CometBFT version, source commit, genesis hash, validator-set hash, node identities, voting power, scenario configuration, logs, finalized height, block hash, and application state commitment. Reports must distinguish passed, failed, skipped, timed out, pending, and not run.
