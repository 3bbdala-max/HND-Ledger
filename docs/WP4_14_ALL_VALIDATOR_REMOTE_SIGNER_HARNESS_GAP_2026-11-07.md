# WP4.14 — All-Validator External Signer Harness Gap

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Status:** Engineering review; no all-validator implementation claimed  
**Scope:** Disposable four-validator CometBFT integration harness

## Finding

The existing four-validator remote-signer integration is intentionally scoped to validator 4. Validators 1–3 retain their local CometBFT FilePV. Extending the current script by merely moving all four private-key files and adding four signer processes is not a safe mechanical change.

The harness has later lifecycle checks that directly inspect validator 4's local `config/priv_validator_key.json` during identity-preservation, identity-substitution, and node-restart recovery checks. A true all-validator external-signer mode must preserve public validator identity evidence without leaving a usable local private-key fallback. It must also restore each remote signer through the same fail-closed state-digest path and prove each CometBFT node reconnects to its own signer after restart.

The current test helper has a single validator-4 signer lifecycle, single signer log, single Unix socket, and validator-4-specific recovery assertions. These are architectural assumptions in the fixture, not just a missing loop.

## Required refactor before claiming coverage

1. Model signer endpoint, process, log, key path, state path, and expected state digest as per-validator records.
2. Separate public validator identity evidence from local private-key material; prove no node can fall back to a local private signer.
3. Start all four signer processes and require a fresh authenticated/connected marker from each before consensus proceeds.
4. Verify each node is configured for its corresponding external signer endpoint and reject any local FilePV private-key fallback.
5. Exercise signer outage for one validator while the other three external signers continue to form quorum.
6. Restart each validator node and its signer in controlled cases; validate the correct validator identity and fail-closed anti-double-sign state digest.
7. Collect all signer processes in cleanup, including replacement processes after outage and node restart.
8. Run the complete four-validator network, partition, recovery, and state-convergence suite in CI.

## Security boundary

Even a passing all-four external-signer integration would establish only that this disposable test topology routes each validator through a separate signer process and survives the tested restart/outage cases. It would **not** establish multi-process or multi-host exclusive ownership, durable distributed fencing, stale-leader rejection, or production-grade failover safety. Those require a separate authoritative ownership design and adversarial crash/partition tests.

## Acceptance status

- Validator 4 external signer integration: **EXERCISED IN CURRENT CI**.
- Validators 1–3 mandatory external signer routing: **NOT YET EXERCISED**.
- Local signer fallback resistance for every validator: **NOT YET PROVEN**.
- All-validator signer restart/recovery matrix: **NOT YET IMPLEMENTED**.
- Distributed single-writer fencing: **OPEN**.
- Production signer approval: **NOT APPROVED**.

No test result is claimed by this review. The implementation must be delivered as a coherent lifecycle refactor with CI evidence, not as a flag-only change.
