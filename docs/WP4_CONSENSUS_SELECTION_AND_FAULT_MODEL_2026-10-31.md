# HND Ledger — WP4 consensus candidate and fault model

**Date:** 2026-10-31  
**Workstream:** WP4 — distributed consensus design  
**Status:** Engineering proposal for review; not a protocol approval  
**Branch:** `phase-0.2-planning`  
**Baseline:** HND v0.2 local ledger and block-chain reference

## 1. Executive decision

Evaluate **CometBFT (Tendermint-style Byzantine Fault Tolerant consensus)** as the first external consensus engine for a controlled HND development network.

Do **not** implement a new consensus algorithm inside the current Python prototype. Keep `hnd_v02/ledger.py` as the deterministic state-transition reference, and investigate integrating that application logic with an established consensus engine. The current HND block format is a local reference format; it is not the CometBFT native block/commit format and cannot be assumed wire-compatible.

This is a candidate selection for an engineering test, not a final commitment to a public network, validator economics, or permissionless participation.

## 2. Why CometBFT is the leading candidate

CometBFT specifies authenticated, round-based consensus using proposals, prevotes, and precommits. A block is committed when the node receives precommits representing **more than two thirds** of the current validator voting power for that block. The protocol may move to another round when a proposal is absent, invalid, late, or fails to gather the required votes.

The official specification states safety and liveness guarantees under a fault bound of less than one third of total validator voting power being malicious or faulty. These guarantees depend on the protocol's network and timing assumptions; they are not a promise that a network always remains available during arbitrary partitions.

Reasons to evaluate it:
- It has an explicit Byzantine fault model rather than merely tolerating stopped processes.
- It defines signed votes, round changes, proposer selection, locking, and commit rules.
- It has an existing implementation and specifications to inspect, reducing the risk of inventing consensus rules.
- Validator membership and voting power can be configured for a controlled test network.

Official references:
- CometBFT specification overview: https://github.com/cometbft/cometbft/blob/main/spec/README.md
- Consensus state-machine specification: https://github.com/cometbft/cometbft/blob/main/spec/consensus/consensus.md
- Validator signing and anti-double-signing rules: https://github.com/cometbft/cometbft/blob/main/spec/consensus/signing.md
- CometBFT validator and Genesis configuration overview: https://github.com/cometbft/cometbft/blob/main/docs/core/using-cometbft.md

References checked: 2026-10-31.

## 3. Proposed first test-network model

| Parameter | WP4 proposal | Reason / boundary |
|---|---|---|
| Network type | Permissioned development network | Membership is explicit during protocol testing |
| Validator count | 4 | Smallest practical equal-weight test set to demonstrate one Byzantine fault |
| Voting power | 1 per validator | No economic stake or token balance is involved |
| Quorum | More than 2/3 of total voting power | For four equal validators, at least 3 votes |
| Validator membership | Fixed in the first test; no on-chain changes | Avoids adding an untested governance surface |
| Validator rewards | None | No incentive or monetary policy is defined |
| Transaction fees | None in the first test | Consistent with the existing v0.2 proposal |
| Real value | None | Test-only transactions and synthetic Genesis allocation |
| Key roles | Dedicated validator-signing keys, separate from account-spending keys | Limits key reuse and separates consensus authority from user funds |

The four validators must be separate processes with independently stored signing state. Running four processes on one computer is useful for deterministic protocol tests, but it does not prove geographic, administrative, infrastructure, or operator decentralization.

## 4. What the four-validator model can and cannot tolerate

With four validators of equal voting power, total power is 4 and the commit threshold is strictly greater than 2/3 of 4. Therefore, a commit requires **3 of 4 votes**.

| Scenario | Available voting power | Expected outcome |
|---|---:|---|
| All four validators healthy | 4/4 (100%) | Can reach quorum |
| One validator crashes or is offline | 3/4 (75%) | Remaining validators can still reach quorum |
| One validator is Byzantine but the other three vote consistently | Up to 3/4 | Within the one-of-four Byzantine test bound; safety depends on correct protocol operation |
| One validator is Byzantine and withholds its vote, while another is offline | 2/4 (50%) | No quorum; chain progress should stop |
| Two validators are Byzantine | 2/4 (50%) | Outside the stated less-than-one-third fault bound; no safety claim |
| Network is partitioned into two groups of two | 2/4 per side | Neither side can commit; halt rather than accept a two-vote commit |

A quorum is a threshold for a decision, not a guarantee that a decision will always be possible. The initial devnet should prefer safety (no conflicting committed blocks) over continued progress when quorum is unavailable.

## 5. Key and validator safety requirements

1. Validator identity must be bound to a dedicated consensus public key registered in the trusted validator set.
2. Consensus signing keys must not be reused as HND account-spending keys.
3. A validator signer must persist anti-double-signing state across restarts. It must not sign conflicting votes for the same height, round, and vote type.
4. Validator-set configuration and voting power must be identical and independently verified by every node at network start.
5. Validator removal, addition, key rotation, or voting-power changes are out of scope until a separate authenticated update mechanism is specified.
6. A node must reject malformed, wrong-chain, wrong-height, wrong-round, or incorrectly signed consensus messages.
7. Do not store real private keys in the public repository, test vectors, logs, or CI output. Use disposable development keys only.

The official CometBFT signing specification describes vote/proposal signing constraints and anti-double-signing protections. HND must rely on a reviewed signer implementation or a carefully reviewed integration; it should not improvise signing-state rules.

## 6. Integration architecture to investigate

Preferred direction:

- **Consensus engine:** CometBFT manages validator communication, proposal/vote rounds, validator-set interpretation, and commit certificates.
- **HND application:** A deterministic application validates HND transaction envelopes and applies the existing ledger state-transition rules.
- **Genesis:** Each node starts from the same authenticated HND Genesis application state and the same explicitly configured validator set. These are related but distinct configuration objects and must both be pinned.
- **Committed state:** HND applies a block only after the consensus engine reports it committed, then deterministically executes the transactions and exposes the resulting application state hash.
- **Persistence/recovery:** Node restart and state synchronization must be tested against committed data, not only local JSON snapshots.

The current `hnd_v02/blocks.py` has no validator signatures, proposer identity, or commit certificate. Do not retrofit a home-made certificate into it and call that CometBFT. The next technical design must map HND's current transaction and state-transition model to the consensus engine's application interface and block lifecycle.

## 7. Required WP4 test matrix

Before any public or financial use, a disposable four-validator test network must exercise at least:

- Normal operation: all validators commit the same sequence of blocks.
- Single-node crash and restart: remaining quorum continues; restarted node catches up.
- One Byzantine validator: malformed proposals, invalid votes, equivocation attempts, and withholding.
- Conflicting proposals and delayed/reordered/duplicated messages.
- Network partition: no partition lacking quorum commits; nodes converge after communication returns.
- Double-sign attempt: signer refuses conflicting signatures after restart.
- Validator key mismatch and unknown-validator messages.
- Invalid HND transaction in a proposed block: no partial application-state mutation.
- Snapshot/recovery and catch-up from a trusted checkpoint.
- Long-run invariant checks: identical committed heights and application hashes across honest nodes.

Acceptance criteria:
1. No two honest validators accept conflicting commits at the same height under the tested fault bound.
2. Honest nodes converge to the same committed block history and HND application-state hash after temporary faults heal.
3. Nodes without quorum do not manufacture a commit or silently switch to a conflicting history.
4. Every failure case is reproducible and logged without exposing private keys.
5. CI runs deterministic unit/integration tests; a separate multi-process test records node-level behavior.

Passing this test matrix would still not be an independent security audit or proof of production readiness.

## 8. Boundaries and unresolved decisions

This proposal does not decide:
- Whether a future public network will be permissioned or permissionless.
- Who may become a validator, how the set is selected, or who can change it.
- Validator rewards, staking, slashing, transaction fees, token distribution, or market value.
- Public Genesis allocation or any real-money issuance.
- A production deployment topology, hosting provider, or legal structure.

A four-validator permissioned devnet is only a safe first engineering test. A later permissionless network would need a distinct validator admission and Sybil-resistance design, plus fresh security, economic, and legal review.

## 9. Next work item

**WP4.1 — CometBFT integration feasibility spike (design only):**
1. Pin a supported CometBFT release after a dependency and maintenance review.
2. Map HND transaction validation and deterministic state execution to the CometBFT application interface.
3. Decide how HND Genesis application state and the CometBFT validator set are authenticated and versioned.
4. Build a disposable four-node local test network only after the interface and key-handling review.
5. Keep all activity on `phase-0.2-planning`; do not change `main`.

## 10. Release boundary

WP4 is consensus design and controlled test planning only. No mainnet, public token issuance, sale, exchange listing, payment integration, custody service, or use of real funds is authorized by this work. Independent security assessment and jurisdiction-specific legal review remain mandatory gates before any public financial use.
