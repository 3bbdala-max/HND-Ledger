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
| C-10a | FilePV reload after persisted Prevote: same H/R/S vote reuses identical signature; conflicting block vote is rejected | Commit `54229259b05ed322f94deaaf87abf532c788c5b3`, Go adapter workflow run `42378294015`, job `128420347444`; `go test ./...` passed | PASS (reload unit test) |
| C-10b | Signing helper process exits immediately after FilePV signs and persists; parent process reloads state and retries/conflicts | Commit `95f6ffb996e77661c809f536981461558d56640a`, Go adapter run `42380149848`, job `128425864594`; `go test ./...` and `go vet ./...` passed; consensusguard package passed | PASS (process-exit unit test; not a CometBFT node crash integration) |
| C-11 | Validator-set update | Old/new set boundary follows protocol rules |
| C-13 | State sync from trusted checkpoint | Replayed state commitment matches checkpoint |
| C-16 | Sustained adversarial mempool load | Bounded resource use and deterministic rejection |

## Evidence required

Each adversarial run must record CometBFT version, source commit, genesis hash, validator-set hash, node identities, voting power, scenario configuration, logs, finalized height, block hash, and application state commitment. Reports must distinguish passed, failed, skipped, timed out, pending, and not run.

| C-17 | Unsupported vote-extension and snapshot methods fail closed in the Python dispatcher | Commit `0ab7294c52f12366aea99a55564b063896e82294`, Python run `42381330354`; exact-commit Python rerun on `41c4eeb4cb61c34b8f1caf4f454de346a06a3a60`, run `42382470345` | PASS |
| C-18 | Four-validator mesh readiness waits for all three P2P peers per validator before partition test; quorum, isolation, recovery scenario completes | Commit `41c4eeb4cb61c34b8f1caf4f454de346a06a3a60`, run `42382470318` | PASS (single CI host) |

## v0.2 consensus scope boundary

- Validator membership is fixed by the initial CometBFT genesis configuration for this release candidate. Dynamic validator-set updates are not implemented or claimed.
- Vote extensions and snapshot/state-sync methods are explicitly unsupported and fail closed; state sync and snapshot restoration are not release features.
- Four-validator liveness and live partition/healing evidence is limited to four separate processes and data directories on one CI runner. Independent hosts, operators, network paths, and production deployment remain unverified.
- Passing local integration tests do not constitute an independent security audit or production-readiness approval.


## IPC and exact-commit regression evidence

| ID | Scenario | Evidence | Result |
|---|---|---|---|
| C-20 | A burst of 32 concurrent local IPC clients receives correctly correlated responses | Commit `7e86e0a21a7e51033d44471376cef45b346b2f40`; Python run `42391236132`; one-node `42391236205`; three-validator `42391236154`; four-validator `42391236188` | PASS (historical 32-client regression; not sustained-load or flood-resistance proof) |
| C-21 | A burst of 64 concurrent local IPC clients receives correctly correlated responses | Commit `bf3f38a79c9bd21ec8079a70a3cc665d91fcb5ec`; Python run `42395157838`; one-node `42395157660`; three-validator `42395157576`; four-validator `42395157681` | PASS (64 short requests; not sustained-load or flood-resistance proof) |
|---|---|---|---|
| C-19 | An incomplete local IPC JSONL request cannot indefinitely block the sequential Python dispatcher; a following valid Info request is served after the 5-second read deadline | Implementation/test commit `a7665df2edcd18ea15417640593eefd7d994ed0d`; Python run `42382630569` | PASS (single stalled-client regression; not flood-resistance proof) |

The subsequent documentation-only commit `03b2b9c6f601525bb810d123de04c64bb06f4494` completed all four exact-commit workflows: Python run `42382868802`, one-node run `42382868836`, three-validator run `42382868758`, and four-validator liveness/recovery run `42382868746`. These confirm the documented code state still passes the current integration suite; the documentation commit did not change runtime code.

IPC timeout scope remains deliberately narrow: the test covers one incomplete client and confirms service resumes after the configured read deadline. Connection-rate limiting, per-client quotas, concurrent flood behavior, and sustained CPU/memory exhaustion remain untested.
