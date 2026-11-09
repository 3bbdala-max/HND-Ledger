# HND v0.2 — Project Closure Register

**Last updated:** 2026-11-09  
**Working branch:** `phase-0.2-planning`  
**Current engineering status:** Prototype remediation in progress; **NOT APPROVED** for production signing, public-network launch, token issuance, or release.

This register tracks repository evidence and unresolved gates. The older `HND_FINAL_CLOSURE_RECORD_v0.1.md` closes only the separate v0.1 educational prototype and is not a v0.2 production approval.

## 1. Completed repository-addressable work

- HND application durable-store schema v4 binds `network_id`, `protocol_version`, `max_amount`, and the pinned HND Genesis hash. Startup rejects mismatched stored identity fields.
- CometBFT v0.40.0 integration is source-pinned to commit `0880b4d378f347ab16e54ec677ff50d803f37d62`; CI verifies that exact source commit.
- The current workflow includes the isolated anti-rollback reference and recovery-control test modules, the JCS compatibility spike, and the CometBFT single-/multi-validator smoke sequence.
- **2026-11-08 state-storage remediation:** `hnd_v02/abci_app.py` now requires a POSIX state directory owned by the service UID with mode `0700`; an existing state file must be a regular, service-owned, single-link file with mode `0600`. Directory/file opens reject symlinks. Writes use directory-relative exclusive temporary-file creation, explicit `0600`, atomic replacement, file fsync, and directory fsync. Unsupported non-POSIX environments fail closed.
- Regression coverage added in `tests/test_v02_abci_app.py` for permissive directory/file modes, state-directory and state-file symlinks, and preservation of `0600` after atomic commit replacement.
- **2026-11-09 strict JSON failure normalization:** `hnd_v02/strict_json.py` now converts the standard-library decoder's `RecursionError` for excessively nested input into the shared `StrictJSONError`. The CLI therefore rejects an over-nested manifest through its normal fail-closed argument error path before starting the ABCI gRPC server. No arbitrary byte/depth cap or consensus parameter was introduced.
- Regression coverage added in `tests/test_v02_strict_json.py` for 20,000-level nested input at the parser boundary and for CLI rejection before server startup.

## 2. Exact evidence for the latest code/test change

- Parser hardening commit: [`55c9634b2db50ccc2729fb84a098df0664ac88b2`](https://github.com/3bbdala-max/HND-Ledger/commit/55c9634b2db50ccc2729fb84a098df0664ac88b2)
- Regression-test commit: [`db2d9aebc6beb4f917ae4e93fe46c19ce5083acd`](https://github.com/3bbdala-max/HND-Ledger/commit/db2d9aebc6beb4f917ae4e93fe46c19ce5083acd)
- Exact-commit workflow run: [`42581430863`](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42581430863)
- Exact run SHA: `db2d9aebc6beb4f917ae4e93fe46c19ce5083acd`; overall workflow: **SUCCESS**.
- `hnd-v02-tests`: **SUCCESS**; all 12 reported job steps completed, including `Run isolated v0.2 tests` and the isolated JCS compatibility checks.
- `cometbft-single-node-smoke`: **SUCCESS**; all reported steps completed, with no failed step. The run includes pinned CometBFT build, Byzantine/equivocation evidence, anti-double-sign persistence/recovery, single-node ABCI, private four-validator integration, external remote signers, and authenticated Noise signer integration.
- The two new deep-nesting regressions are part of the exact successful `hnd-v02-tests` job. The run does not establish a production JSON size/depth policy; that remains deferred to the resource-ownership and protocol decision process.
- Historical state-storage runs `42460127281` and `42460151921` remain recorded as failures at the test-double `os.replace` compatibility step. Their follow-up test correction passed on `a896980358252784d8a485610c70acb809022c45`; those earlier failures are not reclassified as successes.

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

1. Review the cross-store CometBFT/HND recovery implementation against the WP4.14 recovery-height and native-database compatibility audits; identify whether a deterministic, fail-closed mismatch guard can be added without inventing a trust-anchor or snapshot protocol.
2. Keep ABCI local-caller authorization blocked until the independent transport/OS trust-boundary decision is recorded. WP4.17's existing options remain the decision packet; do not enable mutating RPCs or silently choose Unix peer credentials versus mutual TLS.
3. Keep VSP runtime enforcement, production signer integration, real key material, public network deployment, token issuance, release publication, and `main` changes blocked.

**Boundary:** CI success is engineering evidence only. It does not constitute protocol ratification, independent security approval, production readiness, or authorization to launch.
