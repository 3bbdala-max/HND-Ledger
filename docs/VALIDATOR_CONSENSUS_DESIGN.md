# HND validator and consensus design gate

**Status:** design decision record; no consensus implementation is enabled.

## Decision 1: do not invent a consensus protocol

The local prototype must not be promoted into a public chain by adding an ad-hoc voting loop. Consensus is a distributed-systems safety protocol, not a validator count or a periodic block signature.

The next implementation should evaluate an established Byzantine Fault Tolerant protocol rather than create a new one. CometBFT is the leading candidate for evaluation because it has a documented validator model and mature implementation, but this document does not yet select it for HND production use.

## Candidate model for evaluation

A permissioned validator set with voting power is the simplest first model to test. Under the conventional BFT assumption, safety requires less than one-third of total voting power to be Byzantine, and finalization requires a quorum greater than two-thirds. These thresholds must be checked against the exact protocol version and validator-set transition rules before implementation.

A validator is not an account balance or a wallet. It is an independently operated node with:
- A dedicated consensus signing key.
- A configured identity and voting power.
- A verified software version and chain/genesis identity.
- Persistent anti-double-signing state.
- A monitored operator process and network endpoint.

## Required validator behavior

1. Verify chain ID, protocol version, block structure, transaction signatures, nonce order, balances, and state commitment.
2. Never sign two conflicting proposals or votes for the same height/round/step.
3. Persist consensus signing state before acknowledging a signature operation.
4. Reject messages for another chain, stale height, invalid round, or invalid validator-set context.
5. Apply validator-set changes only at the protocol-defined activation height.
6. Recover from restart without forgetting prior signing decisions.

## Test matrix required before any live validator

- 1, 2, 3, 4, and 7 validator configurations.
- One validator offline; multiple validators offline.
- One-third and greater-than-one-third Byzantine voting power scenarios.
- Two conflicting proposals at the same height.
- Duplicate, delayed, reordered, and replayed messages.
- Network partition and later healing.
- Process crash before and after vote persistence.
- Restart with stale database or wrong genesis.
- Validator-set change at an activation boundary.
- Deterministic replay of finalized blocks on all nodes.

## Selection gate

CometBFT is only a candidate. Before adoption, compare:
- Exact protocol and software release compatibility.
- ABCI/application integration model.
- Validator-set update semantics and key management.
- State-sync and upgrade procedures.
- Operational requirements and independent test results.

Until this gate is completed, HND v0.2 remains a local deterministic ledger and no validator or consensus claim should be made.
