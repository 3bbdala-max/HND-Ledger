# HND v0.2 — Project Closure Register

**Last updated:** 2026-11-14  
**Working branch:** `phase-0.2-planning`  
**Current engineering status:** Prototype remediation in progress; **NOT APPROVED** for production signing, public-network launch, token issuance, or release.

This register tracks repository evidence and unresolved gates. The older `HND_FINAL_CLOSURE_RECORD_v0.1.md` closes only the separate v0.1 educational prototype and is not a v0.2 production approval.

## 1. Completed repository-addressable work

- HND application durable-store schema v5 binds `network_id`, `protocol_version`, `max_amount`, `max_block_transactions`, and the pinned HND Genesis hash. Startup rejects mismatched stored identity fields.
- CometBFT v0.40.0 integration is source-pinned to commit `0880b4d378f347ab16e54ec677ff50d803f37d62`; CI verifies that exact source commit.
- The current workflow includes the isolated anti-rollback reference and recovery-control test modules, the JCS compatibility spike, and the CometBFT single-/multi-validator smoke sequence.
- **2026-11-08 state-storage remediation:** `hnd_v02/abci_app.py` now requires a POSIX state directory owned by the service UID with mode `0700`; an existing state file must be a regular, service-owned, single-link file with mode `0600`. Directory/file opens reject symlinks. Writes use directory-relative exclusive temporary-file creation, explicit `0600`, atomic replacement, file fsync, and directory fsync. Unsupported non-POSIX environments fail closed.
- Regression coverage added in `tests/test_v02_abci_app.py` for permissive directory/file modes, state-directory and state-file symlinks, and preservation of `0600` after atomic commit replacement.
- **2026-11-09 strict JSON failure normalization:** `hnd_v02/strict_json.py` now converts the standard-library decoder's `RecursionError` for excessively nested input into the shared `StrictJSONError`. The CLI therefore rejects an over-nested manifest through its normal fail-closed argument error path before starting the ABCI gRPC server. No arbitrary byte/depth cap or consensus parameter was introduced.
- Regression coverage added in `tests/test_v02_strict_json.py` for 20,000-level nested input at the parser boundary and for CLI rejection before server startup.
- **2026-11-10 block-count identity binding:** `max_block_transactions = 1000` is now included in the HND application Genesis protocol configuration and durable-store identity. `InitChain` rejects a mismatched value, and store recovery rejects a persisted value that differs from the running application. The single-node and four-validator disposable fixtures carry the same field. This records the existing deterministic count rule; it does not approve the still-open transaction-byte or aggregate block-byte limits.
- **2026-11-10 evidence-query parser hardening:** the `/evidence` page request now uses the shared `strict_json_loads` decoder rather than direct `json.loads`. Excessively nested JSON is normalized to the adapter's ordinary failed-query response instead of escaping as an uncaught `RecursionError`. Regression coverage exercises a 20,000-level request and asserts a non-zero ABCI query result with the strict parser error.
- **2026-11-14 atomic ABCI query snapshots and bounded cursors:** the evidence query now binds page contents, total count, and committed height under one application lock; continuation carries a committed-height cursor and is rejected after a newer Commit. Account queries return their account view and ABCI response height from one lock snapshot. Query request data is capped at 4,096 bytes before application parsing. Regression coverage includes stale-cursor rejection, offset-only continuation rejection, concurrent Query/Commit ordering, account-height propagation, and oversized request rejection. This is an API resource/consistency control, not a consensus transaction-size rule or history-pruning policy.
- **2026-11-11 supervisor child-environment hardening:** `hnd_v02/cometbft_supervisor.py` now requires an explicit child environment and rejects inherited ambient environments plus `LD_*` and `GLIBC_TUNABLES` overrides. This prevents dynamic-loader injection/behavior overrides from bypassing the executable digest pin. Regression tests assert rejection occurs before activation commit or process spawn. This does not solve privileged same-inode writes or establish the sole production launch path.

## 2. Exact evidence for the latest code/test change

- Parser hardening commit: [`55c9634b2db50ccc2729fb84a098df0664ac88b2`](https://github.com/3bbdala-max/HND-Ledger/commit/55c9634b2db50ccc2729fb84a098df0664ac88b2)
- Regression-test commit: [`db2d9aebc6beb4f917ae4e93fe46c19ce5083acd`](https://github.com/3bbdala-max/HND-Ledger/commit/db2d9aebc6beb4f917ae4e93fe46c19ce5083acd)
- Exact-commit workflow run: [`42581430863`](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42581430863)
- Exact run SHA: `db2d9aebc6beb4f917ae4e93fe46c19ce5083acd`; overall workflow: **SUCCESS**.
- `hnd-v02-tests`: **SUCCESS**; all 12 reported job steps completed, including `Run isolated v0.2 tests` and the isolated JCS compatibility checks.
- `cometbft-single-node-smoke`: **SUCCESS**; all reported steps completed, with no failed step. The run includes pinned CometBFT build, Byzantine/equivocation evidence, anti-double-sign persistence/recovery, single-node ABCI, private four-validator integration, external remote signers, and authenticated Noise signer integration.
- The two new deep-nesting regressions are part of the exact successful `hnd-v02-tests` job. The run does not establish a production JSON size/depth policy; that remains deferred to the resource-ownership and protocol decision process.
- Historical state-storage runs `42460127281` and `42460151921` remain recorded as failures at the test-double `os.replace` compatibility step. Their follow-up test correction passed on `a896980358252784d8a485610c70acb809022c45`; those earlier failures are not reclassified as successes.

## 2A. Exact evidence for 2026-11-10 remediation

- Block transaction-count Genesis/store binding: [commit `2c544f896d547c0f2ea1a1e5a9b080cfad7d0d54`](https://github.com/3bbdala-max/HND-Ledger/commit/2c544f896d547c0f2ea1a1e5a9b080cfad7d0d54).
- Exact-commit CI run: [`42750156287`](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42750156287), exact SHA `2c544f896d547c0f2ea1a1e5a9b080cfad7d0d54`; both `hnd-v02-tests` and `cometbft-single-node-smoke` completed **SUCCESS**.
- Evidence-query parser fix: [source commit `86febdccba92da49b6fdda6340388fd7684d68c2`](https://github.com/3bbdala-max/HND-Ledger/commit/86febdccba92da49b6fdda6340388fd7684d68c2); [regression-test commit `d64678dd22eda68458859e93b42eda4aa12ac2c7`](https://github.com/3bbdala-max/HND-Ledger/commit/d64678dd22eda68458859e93b42eda4aa12ac2c7).
- Exact-commit CI run: [`42777126700`](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42777126700), exact SHA `d64678dd22eda68458859e93b42eda4aa12ac2c7`. At register update, `hnd-v02-tests` completed **SUCCESS** (12/12 steps); `cometbft-single-node-smoke` remained **IN_PROGRESS** at `Build pinned CometBFT binary` (step 7/35), with no failed step reported. Do not treat the overall workflow as successful until the second job completes.
- The new regression is in `tests/test_v02_cometbft_v040_adapter.py`; the existing strict parser implementation already normalizes deep nesting to `StrictJSONError`, which the ABCI query handler maps to a failed response.
- Latest branch head at this evidence update: `d64678dd22eda68458859e93b42eda4aa12ac2c7`. The subsequent closure-register documentation commit is not part of run `42777126700`.


## 2B. Exact evidence for 2026-11-11 supervisor environment hardening

- Source/test commit: [b2ba2ee99572bae1b1008442540fe78b12d616d9](https://github.com/3bbdala-max/HND-Ledger/commit/b2ba2ee99572bae1b1008442540fe78b12d616d9).
- Changed files: [hnd_v02/cometbft_supervisor.py](https://github.com/3bbdala-max/HND-Ledger/blob/phase-0.2-planning/hnd_v02/cometbft_supervisor.py) and [tests/test_cometbft_supervisor.py](https://github.com/3bbdala-max/HND-Ledger/blob/phase-0.2-planning/tests/test_cometbft_supervisor.py).
- Exact-commit workflow run: [42983865839](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42983865839), exact SHA b2ba2ee99572bae1b1008442540fe78b12d616d9; overall workflow **SUCCESS**.
- `hnd-v02-tests`: **SUCCESS**, 34/34 steps. New tests reject `environment=None` and `LD_PRELOAD`, `LD_LIBRARY_PATH`, `LD_AUDIT`, and `GLIBC_TUNABLES` before activation or process creation.
- `cometbft-single-node-smoke`: **SUCCESS**, 37/37 steps; includes pinned CometBFT build, Byzantine/equivocation regression, remote-signer anti-double-sign and crash-recovery probes, single-node ABCI, four-validator integration, external signer recovery, and authenticated Noise signer integration.
- No failed steps or pending jobs remained in this exact-commit run.
- This is bounded supervisor hardening, not proof of a complete production launch boundary. WP4.32's privileged same-inode write/deployment controls, actual sole-launch-path enforcement, frozen Config/VSP binding, independent anti-rollback, and ABCI local-client authorization remain open.
- Branch head at this evidence update: b2ba2ee99572bae1b1008442540fe78b12d616d9.

## 3. Open repository-addressable security and correctness gates

| Priority | Gate | Current evidence / reason still open |
|---|---|---|
| P0 | VSP contract ratification and verifier | WP4.16/WP4.19 record incompatible candidate payload/signature contracts and unresolved expiry, byte-boundary, trust-manifest, activation, and recovery rules. Do not implement against an unratified candidate. |
| P0 | Anti-rollback at actual signature release | WP4.15 records that the offline synthetic anchor is not integrated into CometBFT/FilePV signature release; a durable independent anchor, cross-host fencing, and atomic authorization/HRS/release semantics remain absent. |
| P1 | Mandatory VSP pre-start enforcement | WP4.17 does not establish an unavoidable gate before both HND ABCI and CometBFT startup. This depends on a ratified VSP contract and immutable profile binding. |
| P1 | ABCI local caller authentication/authorization | Loopback-only binding prevents remote exposure but does not authenticate local callers or authorize mutating ABCI methods. Transport/OS trust-boundary selection is still required. |
| P1 | Cross-store CometBFT/HND recovery | Native CometBFT block/state databases are not reconciled against HND app height/hash and an independently authenticated freshness checkpoint before serving/signing. HND ABCI snapshot/state-sync remains explicitly unsupported. |
| P1 | Consensus resource bounds | Application-level transaction and aggregate block byte ceilings are not yet specified and bound consistently to the network profile. Do not invent consensus limits before protocol-owner approval. |
| P1 | Validator identity, trust roots, and lifecycle | Production validator/governance identity enrollment, rotation, revocation, custody, and catastrophic recovery remain unapproved and unimplemented. |

## 4. External prerequisites

- Independent protocol-owner decisions and formal freeze evidence for the protocol specification, VSP schema/signature preimage, expiry and activation policy, CometBFT profile identity, and numeric resource bounds.
- Independent security review of the ratified verifier, signer-release boundary, recovery model, and deployment architecture.
- Selection and independent validation of a durable monotonic trust anchor and cross-host fencing authority; no vendor, hardware, or trust root is selected here.
- Approved validator/governance key custody, dual-control backup/restore, operational incident procedures, and witnessed recovery drills.
- Legal/regulatory review in the intended operating jurisdictions before any public financial activity.

## 5. Next concrete action

1. Supervisor environment hardening is complete on exact commit `b2ba2ee99572bae1b1008442540fe78b12d616d9`; exact-commit run `42983865839` completed both CI jobs successfully. Do not reinterpret this as production approval.
2. Continue the WP4.14 HREC01–HREC09 cross-store CometBFT/HND recovery matrix and identify a deterministic, fail-closed guard that does not invent a trust anchor or snapshot protocol.
3. Keep ABCI local-caller authorization blocked until the independent transport/OS trust-boundary decision is recorded. WP4.17's existing options remain the decision packet; do not enable mutating RPCs or silently choose Unix peer credentials versus mutual TLS.
4. Keep VSP runtime enforcement, production signer integration, real key material, public network deployment, token issuance, release publication, and `main` changes blocked.

**Boundary:** CI success is engineering evidence only. It does not constitute protocol ratification, independent security approval, production readiness, or authorization to launch.


## 2C. Exact evidence for 2026-11-12 single-pending anti-rollback model remediation

- Audit source: §4.1 of [WP4.14 remote-signer anti-rollback implementation boundary audit](WP4_14_REMOTE_SIGNER_ANTI_ROLLBACK_IMPLEMENTATION_BOUNDARY_AUDIT_2026-11-05.md) identified that a distinct operation could replace a current PREPARED record, leaving the first operation unresolved and no longer current.
- Source fix: [`cf1f76833c900ae68b8d07615775f781bbda352b`](https://github.com/3bbdala-max/HND-Ledger/commit/cf1f76833c900ae68b8d07615775f781bbda352b), `hnd_v02/anti_rollback_reference.py`. The synthetic anchor now permits only an exact retry or matching PREPARED-to-COMMITTED transition while a prepare is pending; a distinct operation is rejected. A stale PREPARED operation is not returned as a current retry.
- Regression: [`2ccdd536606542256785d92a7e8e4bd6a7348e0f`](https://github.com/3bbdala-max/HND-Ledger/commit/2ccdd536606542256785d92a7e8e4bd6a7348e0f), `tests/test_v02_anti_rollback_reference.py::test_new_operation_cannot_supersede_pending_prepare`. It asserts rejection, preservation of the first pending record, signing disabled while pending, and successful commit of the original operation.
- The current workflow already includes `tests.test_v02_anti_rollback_reference` under `Run isolated v0.2 tests`.
- Exact-commit run for source change: [43173902846](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43173902846), SHA `cf1f76833c900ae68b8d07615775f781bbda352b`: `hnd-v02-tests` **FAILURE** with zero reported steps; `cometbft-single-node-smoke` **SKIPPED**.
- Exact-commit run for regression: [43173931354](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43173931354), SHA `2ccdd536606542256785d92a7e8e4bd6a7348e0f`: `hnd-v02-tests` **FAILURE** with zero reported steps; `cometbft-single-node-smoke` **SKIPPED**. Rerun attempt 2 had the same result. Both failed HND jobs were created and completed within seconds, had no runner assignment/step records, and exposed no job logs. This is recorded as a CI execution/infrastructure block, not a test assertion failure; no passing test result is claimed.
- Documentation follow-up: [audit addendum commit `f3066af63c319e1aa4effafce6d4977302ecf136`](https://github.com/3bbdala-max/HND-Ledger/commit/f3066af63c319e1aa4effafce6d4977302ecf136).

**Scope boundary:** this closes one state-machine gap in the offline synthetic reference model only. It does not provide a durable independent anchor, production signer integration, signature-release gating, or anti-double-sign certification.

## 5A. Next concrete actions as of 2026-11-12

1. Restore GitHub Actions job execution or obtain an actionable runner/quota diagnostic, then run the full workflow on the exact remediation commit and record the test step result. Do not count the current zero-step failures as code-test results.
2. Once CI is executable, continue the remote-signer model review with the historical-COMMITTED-versus-current-state authorization boundary and add tests only where the intended semantics are already specified.
3. Continue HREC01–HREC09 CometBFT/HND cross-store recovery verification and keep the independent witness/anchor deployment gate open until a separate trust domain and independent review exist.
4. Keep VSP ratification, validator identity, real keys, production signing, public deployment, token issuance, release publication, and all changes to `main` blocked.


## 2D. Exact evidence for 2026-11-12 historical COMMITTED outcome versus current-state authorization

- Audit source: §11 of [WP4.14 pending-operation recovery protocol design](WP4_14_PENDING_OPERATION_RECOVERY_PROTOCOL_DESIGN_2026-11-05.md) identified that historical COMMITTED operation records could be returned by prepare/commit/reconcile paths without proving that the operation remains the latest anchor state.
- Source change: [commit `5575aa4c9ecda6a3b2cad60ef70273982f15240a`](https://github.com/3bbdala-max/HND-Ledger/commit/5575aa4c9ecda6a3b2cad60ef70273982f15240a) adds an explicit `OperationOutcome`, `operation_outcome()`, and `confirm_current()`. Current confirmation checks operation ID, sequence, transaction digest (excluding status), state digest, status, and network/Genesis/validator/signer/schema identity context. Historical COMMITTED retries are explicitly documented as outcome-only; `signing_allowed()` now requires current confirmation.
- Atomic-read follow-up: [commit `0b6522a96c5bf9d651c6e30b086c5059d47e2973`](https://github.com/3bbdala-max/HND-Ledger/commit/0b6522a96c5bf9d651c6e30b086c5059d47e2973) adds `SyntheticAnchor.operation_snapshot()` so the operation-history entry and latest anchor record are observed under one lock rather than through separate reads.
- Regression tests: [commit `83048803723abefb6c0a51465995564141b38746`](https://github.com/3bbdala-max/HND-Ledger/commit/83048803723abefb6c0a51465995564141b38746) covers committing A then B, historical prepare/commit/reconcile retries for A, explicit non-current outcome, rejection by `confirm_current(A)`, and successful current confirmation for B. [Commit `eb546d26d7bb47fa34bcf32434c1a531b3ee2c89`](https://github.com/3bbdala-max/HND-Ledger/commit/eb546d26d7bb47fa34bcf32434c1a531b3ee2c89) covers pairing historical and latest records through the atomic snapshot and anchor-unavailable unknown/blocked behavior.
- The existing workflow includes `tests.test_v02_anti_rollback_reference`; no workflow weakening or bypass was made.
- Exact-commit CI runs: [43175703017](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43175703017) for source SHA `5575aa4c9ecda6a3b2cad60ef70273982f15240a`; [43175769547](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43175769547) for test SHA `83048803723abefb6c0a51465995564141b38746`; [43175942732](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43175942732) for atomic-read source SHA `0b6522a96c5bf9d651c6e30b086c5059d47e2973`; and [43175996065](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43175996065) for latest test SHA `eb546d26d7bb47fa34bcf32434c1a531b3ee2c89`. In each run, `hnd-v02-tests` completed as FAILURE before any step was created (runner_id=0, empty step list); dependent `cometbft-single-node-smoke` was SKIPPED. The latest run has no test-step failure name because no test step ran. This is an execution/runner block, not evidence of a code-test assertion failure. **No passing test result is claimed.**
- Exact-commit run for the documentation update itself: [43176202118](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43176202118), SHA `b67363cbb980562dfe8d02121cf97a59f298846d`, also completed with `hnd-v02-tests` FAILURE, `runner_id=0`, and no steps; `cometbft-single-node-smoke` was SKIPPED. The failure reason is not exposed by the available run/job payload, so do not infer a test failure or a specific quota cause from this record alone.
- Scope boundary: this closes the historical-versus-current semantic gap only in the offline synthetic reference model. It does not create a durable independent anchor, linearize a production signature-release operation, connect the model to CometBFT/FilePV, or certify anti-double-sign safety.

## 5B. Next concrete actions as of 2026-11-12

1. Restore GitHub Actions runner/job execution and obtain the exact reason for zero-step failures; rerun the full workflow on the latest branch HEAD before claiming test acceptance.
2. Continue the HREC01–HREC09 CometBFT/HND cross-store recovery matrix, preserving fail-closed behavior for lower/higher heights and equal-height app-hash mismatch.
3. Keep the independent anchor deployment, production signer release integration, concurrent signer exclusion, crash-boundary proof, VSP ratification, real key custody, public deployment, token issuance, release publication, and all `main` changes blocked pending independent approval and required infrastructure.

## 5C. Explicit ABCI server first-boot versus established-recovery mode (2026-11-13)

- Audit basis: [WP4.14 CometBFT/application recovery-height reconciliation audit](WP4_14_COMETBFT_APPLICATION_RECOVERY_HEIGHT_RECONCILIATION_AUDIT_2026-11-05.md), §5–6, requires established-chain restarts to require an existing HND state file and reserves fresh initialization for an explicit first-boot Genesis ceremony. [WP4.14 durable-state freshness audit](WP4_14_DURABLE_STATE_FRESHNESS_ANTI_ROLLBACK_AND_COMETBFT_RECOVERY_RECONCILIATION_AUDIT_2026-11-07.md), §6 and §8, separately requires fail-closed startup and an independent freshness checkpoint.
- Source change: the ABCI server CLI now requires exactly one of `--initialize-genesis` or `--recovery`; implicit startup mode is rejected. First-boot mode refuses any pre-existing state path, including a dangling symlink. Established recovery passes `require_existing_state=True` and converts a missing state file into an argument error before opening the listener.
- Regression coverage: parser tests reject omitted/conflicting modes; path tests reject existing files and dangling symlinks; CLI tests assert missing recovery state and an existing first-boot path both fail before `start_grpc_server` is called.
- Security boundary: `--initialize-genesis` is an explicit operator mode, **not** authenticated proof of a Genesis ceremony and not a state-freshness anchor. An operator can still select the wrong mode after losing an established store. Independent authenticated freshness, cross-store reconciliation, launcher authorization, and signer gating remain open. No recovery truncation, fallback, or automatic reset was added.
- Pre-change CI baseline: [run 43176370203](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43176370203), SHA `eb2e07d56195fc58e6f59e0015f51d1d5053a0eb`, had `hnd-v02-tests` FAILURE with `runner_id=0` and no steps; dependent `cometbft-single-node-smoke` was SKIPPED. This is not a code-test failure and gives no passing test evidence. Exact post-change CI evidence is recorded after the new branch push; if GitHub again assigns no runner, the test result remains unverified.
- Scope boundary: this closes only the implicit CLI startup-mode ambiguity. It does not close HREC01–HREC09, prove CometBFT native-store reconciliation, or authorize production startup.

### Exact post-change CI result — 2026-11-13

- The explicit-startup-mode source/test commit is [`888afcfadadb9980c2bc80c4c8647412f01903f6`](https://github.com/3bbdala-max/HND-Ledger/commit/888afcfadadb9980c2bc80c4c8647412f01903f6).
- Its exact push run is [`43389422297`](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43389422297). Job `hnd-v02-tests` concluded FAILURE with `runner_id=0`, no start/step records beyond job creation, and no failed step name. The dependent `cometbft-single-node-smoke` job was SKIPPED. The job-log download returned BlobNotFound because no runner log artifact exists.
- Therefore none of the new regression tests or the full HND suite ran in that workflow. This is an execution/runner allocation block, not a passing test result and not an observed assertion failure. No source follow-up was made on the basis of this CI status alone.
- The branch was verified at the source/test commit before this documentation-only evidence addendum. The CI gate remains open until a runner executes both jobs on an exact current commit.

## 5D. Recovery-policy conflict requiring an independent normative decision (2026-11-13)

- Conflicting WP4.14 requirements were confirmed. The [CometBFT/application recovery-height audit](WP4_14_COMETBFT_APPLICATION_RECOVERY_HEIGHT_RECONCILIATION_AUDIT_2026-11-05.md), HREC03, asks the pinned CometBFT replay behavior to be demonstrated when HND is one height behind and requires convergence to the native committed chain. The [durable-state freshness audit](WP4_14_DURABLE_STATE_FRESHNESS_ANTI_ROLLBACK_AND_COMETBFT_RECOVERY_RECONCILIATION_AUDIT_2026-11-07.md), FRESH-05, instead requires quarantine when CometBFT is ahead of HND and authenticated recovery only. Its FRESH-06 also requires rejection of equal-height/different-app-hash state.
- The current single-node smoke harness restores an older, internally valid HND state while retaining CometBFT's newer native store, then observes native replay and convergence. That is useful pinned-version evidence for a replay scenario, but it must not be treated as proof that replay is the approved policy for every stale backup or rollback threat.
- Normative options requiring protocol-owner and independent-review disposition: (A) allow bounded deterministic replay only when the native CometBFT database and chain identity are independently trusted and intact; (B) quarantine on any HND/CometBFT height mismatch and require an explicitly authorized restore; or (C) define a narrowly bounded replay exception with independent checkpoint and app-hash proof. Option A improves recoverability but relies on native-store freshness; B is simpler to fail closed but requires a separate restore ceremony; C adds complexity and must specify exact bounds and trust inputs. No option is selected here.
- Until a signed decision/freeze record resolves this conflict, do not change the smoke harness to claim HREC03/FRESH-05 closure, do not automatically reset/truncate either store, and do not enable signing/listening on ambiguous state. The HREC matrix remains open.
- The documentation-only follow-up commit [`053634d434cb97e3bb54fda1131dcb13300dda60`](https://github.com/3bbdala-max/HND-Ledger/commit/053634d434cb97e3bb54fda1131dcb13300dda60) had exact run [`43389583707`](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43389583707): `hnd-v02-tests` FAILURE, `runner_id=0`, no steps; dependent CometBFT job SKIPPED. No tests ran and no failed step name exists.
- Next priority: obtain the independent recovery-policy decision and restore runner execution. Then implement only the selected fail-closed policy with HREC regression coverage on the exact pinned CometBFT v0.40.0 harness.


## 5E. Atomic ABCI query snapshots and committed-height evidence cursors (2026-11-14)

- Source commits: [`5fb1eb9ce44ce9a080206d64b470ac6dcaa0d42e`](https://github.com/3bbdala-max/HND-Ledger/commit/5fb1eb9ce44ce9a080206d64b470ac6dcaa0d42e) adds atomic evidence-page and account-view snapshot methods; [`734c96e35bf15dccd793724cfe0e7d67e474c575`](https://github.com/3bbdala-max/HND-Ledger/commit/734c96e35bf15dccd793724cfe0e7d67e474c575) binds query response height to the captured snapshot, introduces height-bearing evidence cursors, rejects stale/offset-only continuation, and caps query data at 4,096 bytes.
- Test commits: [`8d544b4989c32f6dc606741e78d2fe2c7f4cfb32`](https://github.com/3bbdala-max/HND-Ledger/commit/8d544b4989c32f6dc606741e78d2fe2c7f4cfb32) adds cursor, stale-height, concurrency, account snapshot, and input-size regression cases; [`50cf9a7642e592e8ac57a12d75cee1ed7f37f530`](https://github.com/3bbdala-max/HND-Ledger/commit/50cf9a7642e592e8ac57a12d75cee1ed7f37f530) corrects the final-page assertion and imports unittest.mock.patch, which was already referenced by existing CLI tests.
- Audit correction: [WP4.14 resource limits audit](WP4_14_ABCI_RESOURCE_LIMITS_QUERY_GROWTH_AND_STATE_SCALABILITY_AUDIT_2026-11-05.md), §8, records that bounded offset/limit pagination already existed on the branch; the new work closes the missing stable-height snapshot/cursor behavior. The old static statement that /evidence always returned the complete journal is superseded for this branch.
- Exact source/test CI run [43572913563](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43572913563), SHA `50cf9a7642e592e8ac57a12d75cee1ed7f37f530`: attempt 1 concluded `hnd-v02-tests` FAILURE and `cometbft-single-node-smoke` SKIPPED, with null step lists. A permitted rerun (attempt 2) was accepted but again ended `hnd-v02-tests` FAILURE before any step record; job `132381309151` has no steps and the dependent CometBFT job was SKIPPED. Log retrieval returned BlobNotFound. No test command or assertion failure is evidenced.
- Audit evidence commit [`7d96d8378448a24cedde23bbd8c7897ae929a4e0`](https://github.com/3bbdala-max/HND-Ledger/commit/7d96d8378448a24cedde23bbd8c7897ae929a4e0) had exact push run [43572948661](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43572948661): HND job FAILURE with null steps; CometBFT job SKIPPED.
- Latest closure-register commit [`84c54ce89132c1663a95d1854e72621757e5ee75`](https://github.com/3bbdala-max/HND-Ledger/commit/84c54ce89132c1663a95d1854e72621757e5ee75) had exact run [43572978420](https://github.com/3bbdala-max/HND-Ledger/actions/runs/43572978420), attempt 1: HND job FAILURE with null steps; CometBFT job SKIPPED. A permitted rerun (attempt 2) again failed before step creation; job `132381246182` has no steps and logs return BlobNotFound. These are GitHub Actions execution/provisioning failures, not diagnosed code-test failures. No test pass is claimed.
- Remaining resource gates: protocol-owner-approved per-transaction and aggregate block byte limits; exact validator-wide CometBFT/gRPC receive settings; archival/checkpoint policy preserving app-hash linkage; long-history commit/restart benchmarks; and multi-replica query/recovery tests. No consensus limit, pruning rule, or recovery policy was selected.
- Next repository priority: inspect the latest branch/PR state and continue the HREC/launcher boundary only where current source and approved invariants make the change determinate. The Actions execution block must be resolved separately; do not treat zero-step failures as test results.
