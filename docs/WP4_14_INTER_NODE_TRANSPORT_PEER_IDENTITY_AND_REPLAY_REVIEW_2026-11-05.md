# HND v0.2 — Inter-node transport, peer identity, and replay-boundary review

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Status:** Static source/test review and verification plan only  
**Reviewed files:** `scripts/hnd_peer_relay.py`, `tests/test_v02_tcp_peer_relay.py`, `tests/test_v02_four_abci_replica_evidence.py`, `tests/test_v02_four_replica_state_convergence.py`, and `tests/test_v02_cometbft_v040_adapter.py`  
**Safety boundary:** The reviewed relay is a disposable loopback test utility. This review does not establish authenticated production peer transport.

## 1. Executive result

The inspected repository evidence demonstrates useful test infrastructure for four independent ABCI application instances and a loopback-only directed TCP relay. It does **not**, by itself, establish that production peers authenticate one another, that peer identities are bound to validator identities, or that the HND application has its own replay-protected authenticated inter-node protocol.

The four-replica ABCI evidence test directly sends the same requests to four local gRPC endpoints. Its own module documentation distinguishes this from the separate CometBFT P2P integration. The relay forwards bytes between loopback TCP sockets; it does not parse, authenticate, sign, encrypt, or replay-filter protocol messages.

## 2. Positive controls observed

1. `DirectedTCPRelay` rejects non-loopback listen and target hosts, making its intended test-only scope explicit.
2. The relay can disable a directed route and forcibly close active connections; tests cover disable/re-enable and rejection of new routes while disabled.
3. The four-ABCI-replica test creates four separate application instances with separate state files, compares committed evidence journals and application hashes, and restarts one application from durable state.
4. The four-replica state-convergence test checks equal inputs, detects a same-height divergent application hash, and labels itself as an application-layer test rather than a consensus/Byzantine-fault proof.
5. The test suite exercises real local gRPC calls and concurrent Info requests.
6. The test code explicitly identifies the separate WP4.11 integration as the location for real CometBFT P2P equivocation delivery.

These are meaningful local integration controls, but they do not establish secure peer identity or production network behavior.

## 3. Findings

### P01 — No HND-level peer authentication was identified in the reviewed files

The reviewed HND relay is raw TCP forwarding, and the ABCI gRPC server uses an insecure listener. No HND-level peer certificate validation, mutual TLS, signed peer handshake, or binding between a transport identity and a validator identity appears in these reviewed components.

**Impact:** a network deployment must rely on CometBFT's separately configured P2P security and operational network controls. The HND ABCI adapter itself does not authenticate the caller as a particular validator.

**Required action:** inspect and pin the exact CometBFT node configuration and P2P transport security for the intended deployment. Document node key ownership, peer ID derivation, private-network allowlists, seed/persistent-peer policy, and how validator consensus identity is kept distinct from P2P node identity. Do not invent a second HND handshake unless a concrete protocol requirement justifies it.

### P02 — Four-replica ABCI fan-out is not a P2P network test

The four-replica evidence test constructs four local applications and sends the same ABCI requests directly to each endpoint. It proves application-level deterministic handling under identical inputs, not that consensus messages traverse a real four-node P2P network or that each peer authenticated the others.

**Required action:** retain this test's narrow label. Treat the separate WP4.11 CometBFT P2P integration as a distinct evidence item and verify its exact topology, node keys, peer connections, fault injection, and assertions before making any P2P claim.

### P03 — The TCP relay tests connectivity interruption, not message authenticity or replay resistance

The relay forwards arbitrary bytes and can sever connections. The tests prove route forwarding and interruption behavior. They do not mutate a message, replay a prior message, spoof a peer identity, alter a validator mapping, or validate transport encryption.

**Required action:** add P2P integration tests that capture and replay protocol-level traffic where the test harness permits, inject malformed or delayed messages, and confirm that CometBFT rejects invalid signatures/peer identities and does not accept stale consensus messages as new valid votes. Use protocol-native test hooks rather than interpreting raw relay success as authentication evidence.

### P04 — Peer identity and validator identity are different trust domains

The evidence test's misbehavior object includes a validator address and voting power, while P2P transport peers are not identified by those application fields. A peer ID, validator consensus address, and HND account address must not be treated as interchangeable.

**Required action:** maintain an explicit mapping and lifecycle for:
- CometBFT P2P node identity and node key;
- validator consensus public key/address and voting power;
- HND transaction account public key/address.

Specify who approves each mapping, how changes are authenticated, and how revocation or validator-set updates take effect. Never authorize validator actions solely from a TCP source address or an HND account ID.

### P05 — Replay protection is only demonstrated at the transaction-envelope layer in reviewed HND code

The transaction envelope binds network ID, protocol version, sender, recipient, amount, and nonce under Ed25519. That is a useful transaction-level replay boundary. It is not proof of replay protection for P2P messages, CometBFT votes, peer handshakes, or administrative control messages; those are governed by their respective protocols and configurations.

**Required action:** document the replay boundary per message class. Verify CometBFT's native chain ID, height/round/step, validator-set, signature, and peer-session checks in the pinned version and integration tests. Any HND-specific administrative message must have its own domain separation, unique sequence/nonce, expiry policy, and authenticated sender authorization.

### P06 — Local gRPC test security differs from deployment security

Tests use `grpc.insecure_channel` to connect to loopback test servers. This is appropriate for isolated local tests but is not evidence of authenticated or encrypted remote ABCI transport.

**Required action:** keep ABCI gRPC loopback-only or behind a separately secured private boundary. If remote ABCI is required, implement and test authenticated encrypted transport, client authorization, and network policy before exposing it.

## 4. Required integration evidence

| ID | Scenario | Required evidence |
|---|---|---|
| NET01 | Four real CometBFT nodes start with distinct node keys and pinned chain/genesis | Node IDs and chain configuration recorded; no identity reuse |
| NET02 | Nodes establish P2P connections | Authenticated peer identities and expected peer topology observed |
| NET03 | A node presents an unexpected or disallowed peer identity | Connection rejected or isolated according to explicit policy |
| NET04 | Validator consensus key differs from P2P node key | Mapping remains explicit; neither identity is substituted for the other |
| NET05 | Delayed/replayed vote or stale consensus message is injected | Native CometBFT validation rejects it; evidence records reason |
| NET06 | One peer disconnects and reconnects | Catch-up and state convergence verified without bypassing consensus |
| NET07 | A peer sends malformed or excessive traffic | Bounded resource use, rejection, and observable logs |
| NET08 | P2P partition creates conflicting local views | No claim of finality until consensus resolves; safety/liveness evidence captured |
| NET09 | ABCI endpoint is probed from outside its permitted boundary | Connection is blocked; no unauthenticated remote control |
| NET10 | Node/validator key rotation or revocation is exercised | Old identity loses authority under documented transition rules |

These are future acceptance checks, not results from this review.

## 5. Evidence required from WP4.11

Before accepting the separate P2P integration as evidence, inspect and archive:
- exact CometBFT binary/version and configuration;
- node IDs and a record that node private keys are distinct;
- chain ID and independently pinned genesis hash;
- persistent-peer/seed configuration and expected topology;
- actual P2P connection logs for all four nodes;
- the injected equivocation/evidence scenario and the node that receives it;
- committed evidence journal and application-hash comparison across nodes;
- partition/restart/rejoin outcomes and any safety/liveness limitations.

## 6. Evidence and release status

This was a static source/test review. No tests, network scans, or four-node P2P integration were executed in this review. P01–P06 are review findings and scope boundaries; NET01–NET10 are proposed acceptance checks.

Current evidence supports loopback relay behavior and deterministic four-ABCI application fan-out. It does not support a claim that HND's peer transport is independently authenticated or that the production network is resistant to P2P replay, spoofing, partition, or Byzantine behavior. Production networking and release authorization remain gated.
