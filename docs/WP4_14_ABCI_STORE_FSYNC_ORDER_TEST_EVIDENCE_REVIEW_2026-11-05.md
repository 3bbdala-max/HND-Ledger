# HND v0.2 — ABCI store fsync-order test-evidence review

**Date:** 2026-11-05  
**Workstream:** WP4.14 — Durable state and restart review  
**Branch:** `phase-0.2-planning`  
**Status:** Documentation-only static review. No source, test, or workflow files changed.

## 1. Executive result

The current ABCI application-store writer has the expected POSIX durability sequence in source:

1. write a sibling temporary file;
2. flush the userspace buffer;
3. fsync the temporary file;
4. atomically replace the destination;
5. fsync the parent directory.

The inspected tests do not fully prove that ordering. One test checks only the number of `fsync` calls. Another test named `test_restart_after_durable_replace_recovers_committed_height_and_hash` raises immediately after the real `os.replace` call, which interrupts execution **before** the parent-directory fsync in `_write_store()`.

Therefore, the implementation sequence looks correct by static inspection, but the existing test evidence does not demonstrate the full file-fsync → replace → directory-fsync ordering or the behavior when directory fsync itself fails.

This is a test-evidence gap, not a finding that the current writer uses the wrong order.

## 2. Source reviewed

At the reviewed branch head:

- `hnd_v02/abci_app.py`
  - `HNDABCIApplication._write_store()`
  - `HNDABCIApplication.commit()`
- `tests/test_v02_abci_app.py`
  - `test_commit_fsyncs_state_file_and_parent_directory`
  - `test_restart_after_durable_replace_recovers_committed_height_and_hash`
  - `test_commit_storage_failure_leaves_old_committed_state`

Static inspection only. No test command was run.

## 3. Exact test-evidence limitation

### 3.1 fsync call-count test

`test_commit_fsyncs_state_file_and_parent_directory` wraps `os.fsync` and asserts a call count of two on POSIX and one elsewhere.

That proves the expected number of calls for the exercised path, but it does not independently assert:

- the first fsync targets the temporary state file;
- `os.replace` occurs after that file fsync;
- the second fsync targets the parent directory;
- the directory fsync occurs after the replace;
- the directory descriptor is closed even when fsync raises.

### 3.2 Restart-after-replace test

The restart test replaces `os.replace` with a wrapper that performs the real rename and then raises a simulated process-loss exception. In the production writer, the parent-directory fsync is after `os.replace`; raising from the wrapper prevents that later fsync from running.

The test therefore demonstrates that, on the test filesystem used, a new process can read the renamed state file after this simulated interruption. It does **not** demonstrate that the directory entry survived a completed directory fsync or a real power-loss boundary.

The test name's phrase “durable replace” is stronger than the exact operation it simulates: it tests a successful rename followed by interruption before directory synchronization.

### 3.3 Failure-path coverage

The storage-failure test injects an `os.replace` failure and verifies the old committed state remains available for retry. The inspected tests do not inject a failure specifically at the parent-directory fsync after the destination has already been replaced.

That post-replace failure is an important distinct state: the new file may be visible to the running process, but the writer cannot claim that the directory-entry update has reached the requested durability boundary.

## 4. Recommended acceptance tests

Add these tests only after explicit authorization to modify tests:

| ID | Injection / assertion | Required evidence |
|---|---|---|
| ABCIDUR01 | Instrument file fsync, replace, and directory fsync | Assert exact order: file fsync → replace → directory fsync |
| ABCIDUR02 | Inspect descriptors passed to fsync | First descriptor is the temporary file; second is the parent directory |
| ABCIDUR03 | Fail temporary-file fsync | Replace is not called; previous destination remains intact |
| ABCIDUR04 | Fail parent-directory fsync after successful replace | Commit reports the storage error; in-memory committed height is not advanced in that process; pending state remains available for controlled retry |
| ABCIDUR05 | Restart after injected post-replace directory-fsync failure | Restart accepts only a complete, internally verified old or new store; never a partial/corrupt store |
| ABCIDUR06 | POSIX and non-POSIX behavior | Platform-specific durability contract is explicit; do not assume directory fsync semantics where unsupported |

For ABCIDUR04, the test must not label the result “not committed” at the filesystem level: the replacement has already occurred. The accurate state is an uncertain durability outcome requiring restart/reconciliation or an exact idempotent retry.

## 5. Recommended disposition

1. Keep the current source order unchanged unless a separate implementation review finds a defect.
2. Strengthen the tests to assert operation ordering and descriptor targets, not only call counts.
3. Rename or clarify the restart test so it states that it simulates interruption immediately after rename and before directory fsync.
4. Record the exact platform/filesystem used for crash-oriented tests.
5. Keep local filesystem tests separate from the CometBFT/HND cross-store recovery matrix; neither substitutes for the other.

## 6. Release boundary

This review does not certify power-loss behavior across filesystems, storage controllers, virtual machines, or operating systems. It records a bounded gap in test evidence. Cross-store CometBFT recovery, independent anti-rollback protection, and production durability remain separate open gates.
