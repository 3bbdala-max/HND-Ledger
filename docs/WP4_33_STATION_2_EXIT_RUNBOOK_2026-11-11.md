# WP4.33 — Station 2 Exit Runbook and Acceptance Gates

**Date:** 2026-11-11  
**Base commit:** `e6b20622fbba080817640c220aa5f41f9b3b643b`  
**Disposition:** Execution plan only. This document does not claim that the open production controls are implemented or approved.

## Objective

Close Station 2 with evidence, not by weakening its acceptance criteria. The already-merged recovery matrix (PR #46) remains accepted and is not reopened absent a regression. Work is limited to the remaining anti-rollback, pre-start authorization, and sole-launch-path controls.

## Fixed decisions for the implementation sequence

1. SQLite remains test/reference-only. It must never be labelled a production anti-rollback anchor.
2. Fail closed if the independent anchor, trust root, Config-v1 identity, operator acknowledgements, executable identity, or recovery checkpoint cannot be authenticated.
3. Do not freeze or implement Config-v1 normative behavior until the owner decision record is explicitly approved.
4. Do not expose ABCI, CometBFT RPC/P2P, or signer endpoints before authorization completes.
5. Do not change the already-passing HREC04–HREC06 recovery behavior except to fix a demonstrated regression.

## Work packages, in shortest safe order

### WP4.34 — Specify the independent anchor contract

Deliver a versioned deployment contract for an anchor service in a separate administrative and failure domain. Required properties:

- linearizable compare-and-advance per namespace;
- durable acknowledgement: a successful response survives process, host, and replica restart;
- quorum/consensus-backed replication or hardware-backed monotonic state, with documented failure assumptions;
- authenticated operator and client identities, certificate rotation/revocation, and pinned trust roots;
- independent backups/recovery that cannot silently restore an older accepted sequence;
- auditable conflict, unavailable, stale, and recovery outcomes;
- concurrent-writer, crash-after-commit, partition, stale-replica, replica-rollback, and restore-from-backup tests.

A single-host SQLite database, ordinary filesystem snapshot, or mock backend does not satisfy this contract.

**Exit evidence:** architecture and threat model reviewed; implementation demonstrates linearizable CAS under concurrency and durability across the stated crash/rollback tests; independent operator/key custody documented.

### WP4.35 — Enforce pre-start authorization

Build one orchestration entrypoint that accepts an immutable activation bundle and performs, in order:

1. verify pinned trust root and trust-manifest chain;
2. verify VSP profile signatures, schema/version, predecessor/successor sequence and digest;
3. verify approved Config-v1 identity and exact CometBFT v0.40.0 profile/binary digest;
4. verify unanimous operator acknowledgements and activation-height policy;
5. read and atomically advance both anti-rollback namespaces through the independent anchor;
6. retain verified bytes and executable descriptor through process creation;
7. only then start ABCI and CometBFT.

Any failure must leave no child process and no listening socket. The ABCI server must not start independently in production mode. Test-only direct process launchers remain clearly isolated as test harnesses.

**Exit evidence:** integration tests prove every negative branch starts zero children and opens zero sockets; positive branch launches only the pinned artifact; process-tree and socket inspection confirms there is no alternate production path.

### WP4.36 — Make activation atomic and recoverable

Use a backend whose transaction covers profile activation and both monotonic namespace advances. Define intent states and recovery rules for crashes before commit, after durable commit but before response, and during process launch. Prove idempotent restart and witnessed recovery for stuck intent/key loss.

**Exit evidence:** fault-injection matrix, durable transaction proof, witness procedure, and restart tests against the independent anchor.

### WP4.37 — Deployment and independent review

- Run services under dedicated least-privilege identities.
- Make executable, configuration, trust roots, and service units root-controlled and immutable to the runtime account.
- Enforce the sole launcher using OS/service policy; deny direct production invocation.
- Separate operator, witness, anchor, and signing key custody.
- Complete external security review and record findings/remediation.
- Enable protected branch/ruleset and required CI checks before production changes.

**Exit evidence:** reproducible deployment, policy tests, key-custody evidence, signed review report, and all findings closed or explicitly risk-accepted by the authorized owner.

## Station 2 final acceptance checklist

| Gate | Required evidence | Current disposition |
|---|---|---|
| Recovery matrix HREC04–HREC06 | PR #46 merged; exact merge-commit CI passed | Accepted |
| Independent anti-rollback anchor | Separate trust/failure domain; durable linearizable CAS tests | Open |
| Atomic activation backend | Atomic profile + both namespaces; crash/recovery evidence | Open |
| Pre-start authorization | Fail-closed orchestration before all listeners/processes | Open |
| Sole production launch path | OS/service enforcement and negative bypass tests | Open |
| Frozen Config-v1 and CometBFT profile | Explicit owner decision and complete schema/golden vectors | Pending |
| Production deployment and review | Hardened deployment, key custody, independent review | Open |

## Release rule

Station 2 may be marked complete only when every required gate above has evidence attached to the exact reviewed commit and the authorized owner has approved the pending normative decisions. CI success alone is insufficient. Until then, the project remains experimental and must not be represented as ready for a public network, real funds, or production signing.

## Immediate next implementation

Start WP4.34 by selecting and threat-modelling the independent anchor architecture. Do not begin with a SQLite adapter or a mock advertised as production. In parallel, implement WP4.35's fail-closed orchestration seam only after its inputs and trust decisions are frozen; keep all network listeners closed until that seam succeeds.
