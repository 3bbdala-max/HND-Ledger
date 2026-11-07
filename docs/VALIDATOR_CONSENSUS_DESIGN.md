# HND validator and consensus design

**Status:** CometBFT v0.40.0 is selected and integrated for local testing. Production validator governance and operations are not yet designed or enabled.

## Decision: use an established consensus engine

HND does not implement a custom voting loop. CometBFT owns validator voting, proposal gossip, and block consensus. The Go ABCI adapter is a transport layer; Python owns HND transaction and state-transition rules.

## Current test topology

The CI integration creates three CometBFT validators with distinct node homes and validator identities. Each validator has its own Python application process, SQLite database, and Unix IPC socket. The workflow tests a funded development genesis, a signed transfer, matching application hashes, and restart recovery.

These are three processes on one CI runner, not three independent operators or hosts. The test does not cover Byzantine behavior, network partitions, or validator-set governance.

## Consensus assumptions

CometBFT uses a voting-power-based BFT consensus protocol. The eventual HND validator policy must explicitly adopt and validate the exact pinned release's safety and liveness assumptions, including the conventional less-than-one-third Byzantine voting-power safety bound and quorum rules. A local three-node success is not a proof of those assumptions.

## Validator identity and operations required before public use

A production validator requires:
- Dedicated consensus signing key stored outside the application database.
- Explicit validator identity and voting power.
- Chain ID and genesis verification before joining.
- Persistent anti-double-signing state and safe restart behavior.
- Access-controlled network endpoint and firewall policy.
- Secure backup, recovery, rotation, and revocation procedures.
- Monitoring, alerting, upgrade coordination, and incident response.

None of these operational procedures is complete for public use.

## Remaining consensus test gate

- Conflicting proposals at the same height and round.
- Duplicate, delayed, reordered, and replayed votes.
- Byzantine voting-power scenarios inside and outside the documented fault bound.
- Network partition, packet loss, validator downtime, and healing.
- Crash before/after vote persistence and restart without double-signing.
- Validator-set update at an activation boundary.
- State sync, snapshot recovery, and deterministic replay across independent hosts.
- Multi-host deployment operated by independent parties.

## Selection and release gate

CometBFT v0.40.0 is the selected integration engine, not a final public-network deployment decision. Before any public use, freeze the validator admission model, voting-power governance, genesis process, upgrade policy, key custody, state sync, monitoring, and legal/economic framework. Complete independent security review and adversarial testing.
