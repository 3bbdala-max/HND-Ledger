# HND consensus test matrix

This is a planned test matrix. None of these distributed-consensus tests are claimed as executed.

| ID | Scenario | Expected invariant |
|---|---|---|
| C-01 | Valid proposal and quorum | All honest nodes finalize the same block |
| C-02 | Two conflicting proposals at one height | Honest nodes do not finalize conflicting blocks |
| C-03 | Duplicate vote | Duplicate message has no additional voting weight |
| C-04 | Replay vote from old height | Message rejected |
| C-05 | Vote from wrong chain ID | Message rejected |
| C-06 | Byzantine voting weight below one-third | Safety maintained under protocol assumptions |
| C-07 | Byzantine voting weight at or above one-third | Safety/liveness guarantees treated as outside the fault bound; system must not claim normal guarantees |
| C-08 | Network partition | No conflicting finalization; liveness may pause |
| C-09 | Partition heals | Nodes converge according to the selected protocol |
| C-10 | Validator crashes after signing | Restart does not permit conflicting signature |
| C-11 | Validator-set update | Old/new set boundary follows exact protocol rules |
| C-12 | Wrong genesis on node | Node refuses to join |
| C-13 | State sync from trusted checkpoint | Replayed state commitment matches checkpoint |
| C-14 | Malformed or oversized message | Bounded rejection without process failure |
| C-15 | Deterministic replay | Every honest node derives identical application state |

## Evidence required

Each run must record software version, genesis hash, validator-set hash, node identities, voting power, scenario configuration, logs, finalized height, block hash, and state commitment. A test report must distinguish passed, failed, skipped, timed out, and not run.
