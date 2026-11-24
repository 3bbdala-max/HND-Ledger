# HREC local journal prototype

Status: experimental, isolated on branch `hrec-journal-prototype`.

## Included

- `hnd_v02/hrec_journal_model.py`: deterministic operation state machine.
- `hnd_v02/hrec_sqlite_journal.py`: local SQLite persistence using WAL,
  FULL synchronous mode, immediate write transactions, and startup replay.
- `tests/test_hrec_journal_model.py`: state-machine invariants.
- `tests/test_hrec_sqlite_journal.py`: local persistence and reopen tests.
- `hnd_v02/hrec_checkpoint_anchor.py`: bridge from finalized HREC operation identity to the existing external monotonic-anchor contract.
- `tests/test_hrec_checkpoint_anchor.py`: checkpoint bootstrap, CAS, idempotency, lost-response reconciliation, and SQLite reference-backend tests.

## State progression

`PREPARED -> APPLICATION_COMMITTED -> CONSENSUS_COMMITTED -> CHECKPOINT_PUBLISHED -> FINALIZED`

Transitions advance one phase at a time. Only one operation may be pending.
Operation IDs are idempotent only when the immutable operation identity matches.
Sequence and block height must each advance by exactly one from the configured
anchor. The configured anchor is persisted and must be supplied identically
when reopening the database.

## Durability boundary

The SQLite adapter configures WAL and `synchronous=FULL`, and commits each
transition in a SQLite transaction. This provides a local persistence reference
for testing. It does not prove survival against storage hardware that lies about
flushes, filesystem bugs, database replacement, privileged rollback, or loss of
the entire host. The database's own anchor is not independent of the database.

## Explicit non-goals

This prototype is NOT:
- an independently administered monotonic checkpoint authority;
- a cross-store atomic commit protocol for HND and CometBFT;
- a CometBFT v0.40.0 patch or post-commit hook;
- a signer fence or mandatory startup gate;
- authorization for production signing, public deployment, funds, or token use.

## Required next gates

1. Run both HREC test modules on this branch and retain exact commit/run evidence.
2. Add corruption and process-kill tests around SQLite transaction boundaries.
3. Provision the existing mTLS remote monotonic-anchor service in a separately administered failure domain; initialize hrec-checkpoint sequence 0 from the independently verified Genesis digest.
4. Integrate the HREC bridge with a reviewed CometBFT post-commit boundary. Do not
   publish before both HND and CometBFT durable commits are confirmed.
5. Add a mandatory fail-closed startup gate before any CometBFT or ABCI listener
   starts, including proof that no alternate launch path bypasses it.
6. Test crash recovery across every boundary and demonstrate signer fencing.

No production readiness is claimed until all gates pass on the same reviewed
source revision.
