# HND v0.2 — Standalone ledger durability boundary review

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Durable state and restart review  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation-only static review. No source, test, or workflow files changed.

## 1. Executive result

The ABCI application store and the standalone `HNDLedger.save()` path do not currently provide the same filesystem durability sequence.

The ABCI application writer in `hnd_v02/abci_app.py` writes a sibling temporary file, flushes and fsyncs the file, atomically replaces the destination, and on POSIX opens and fsyncs the parent directory. The standalone ledger writer in `hnd_v02/ledger.py` flushes and fsyncs its sibling temporary file and atomically replaces the destination, but does not fsync the parent directory after the rename.

On filesystems/platforms where directory-entry durability requires a directory fsync, a power loss after the rename can leave the standalone save's new directory entry not durably recorded. The atomic rename protects readers from observing a partially written file during normal operation; it is not by itself a guarantee that the rename survives sudden power loss.

This is a bounded finding about the standalone ledger persistence API. It does not establish a defect in the ABCI application's `Commit` persistence sequence.

## 2. Source reviewed

At the reviewed branch head:

- `hnd_v02/abci_app.py` — `_write_store()` and `_load_store()`
- `hnd_v02/ledger.py` — `HNDLedger.save()` and file restoration
- `tests/test_v02_abci_app.py` — commit storage-failure and restart-after-replace tests
- `tests/test_v02_ledger.py` — standalone file save/load tests

This is static source/test-definition inspection. No test command was run.

## 3. Exact difference

| Persistence step | ABCI application store | Standalone ledger save |
|---|---|---|
| Temporary file in destination directory | Yes | Yes |
| Flush userspace buffer | Yes | Yes |
| fsync temporary file | Yes | Yes |
| Atomic replace | Yes | Yes |
| fsync parent directory after replace on POSIX | Yes | **No** |
| Restart verification by replaying ledger history | Yes, through ledger snapshot restore | Yes |

The relevant distinction is the missing parent-directory synchronization in `HNDLedger.save()`. The standalone persistence tests verify round-trip restoration and corruption rejection, but the inspected tests do not inject a crash/power-loss boundary around the rename and directory synchronization.

## 4. Risk and scope

- **Risk:** after a successful return from `HNDLedger.save()`, a sudden power loss may, depending on filesystem and platform semantics, lose the rename even though the temporary file's contents were fsynced.
- **Scope:** standalone ledger snapshots saved through `HNDLedger.save()`.
- **Not established:** that the ABCI `Commit` writer has the same omission; its implementation explicitly fsyncs the parent directory on POSIX.
- **Not established:** a data-loss event on a particular deployed filesystem. This is a durability-contract gap identified by source inspection.

## 5. Recommended disposition

Choose and document one of these paths before treating standalone ledger persistence as crash-durable:

1. **Strengthen the implementation:** after successful `os.replace`, fsync the destination's parent directory on supported POSIX systems, using the same carefully reviewed error handling and cleanup discipline as the ABCI store writer.
2. **Narrow the contract:** explicitly label `HNDLedger.save()` as an atomic snapshot convenience API that does not promise power-loss durability, and prohibit its use as the authoritative production/validator state store.

Do not silently infer the stronger guarantee from the word “atomic”. Keep the ABCI store and standalone snapshot guarantees separately stated.

## 6. Required verification if implementation is authorized

- Inject failure before file fsync: destination remains the previous valid snapshot.
- Inject failure at/after replace but before directory fsync: process must report uncertain durability; restart must either verify a complete old or complete new snapshot, never accept a partial/corrupt snapshot.
- Verify directory fsync is attempted on supported POSIX platforms.
- Verify unsupported platforms follow an explicit documented durability contract.
- Run the standalone ledger persistence tests and ABCI persistence/restart tests in the authorized environment; record exact command, runtime, commit, and output.

These are proposed tests only. No implementation or test execution is claimed.

## 7. Release boundary

This review does not certify filesystem behavior across all operating systems, filesystems, storage controllers, or virtualized environments. Production durability still requires a declared deployment platform/filesystem contract, crash testing, and independent review. Public network and production release gates remain closed.
