# HND ABCI++ transport

Status: implemented and exercised with CometBFT v0.40.0 in local CI.

## Process topology

CometBFT v0.40.0 connects over loopback TCP to the Go ABCI adapter. The Go adapter connects over a private Unix-domain socket to the Python HND application. Python persists the ledger in a per-validator SQLite database.

The Go adapter is a transport layer only. Python remains the reference state machine. The Go ABCI listener rejects non-loopback addresses; the Python IPC endpoint is not exposed on TCP.

## Method mapping

| ABCI method | HND behavior |
|---|---|
| Info | Committed height and app hash |
| InitChain | Validate chain ID and canonical genesis; persist genesis state and marker atomically |
| Query | Read-only latest account and ledger-info paths; no proofs/historical reads |
| CheckTx | Encoding, chain ID, and signature admission only |
| InsertTx / ReapTxs | Bounded in-memory mempool |
| PrepareProposal | Deterministic valid transaction selection |
| ProcessProposal | Full ordered proposal validation |
| FinalizeBlock | In-memory candidate, no durable write |
| Commit | Atomic block persistence |
| ExtendVote / VerifyVoteExtension | Unsupported/disabled |
| Snapshot methods | Unsupported; no state-sync snapshot format |

## Invariants

- Same committed history must yield identical app hashes.
- PrepareProposal and ProcessProposal do not mutate committed state.
- FinalizeBlock does not persist.
- Commit persists before returning.
- Startup replays and verifies persisted blocks before reporting height/hash.
- CheckTx is weaker than proposal validation; it does not reserve nonce or balance.
- Mempool state is disposable and not consensus state.

One-node restart and three-validator signed-transfer integrations passed on commit 1c62d3cad548315b8cecb811edd76ee6b93808af. Query unit tests passed on a6c5250905d0861c5d3a62dd766d957742080b1c; RPC-level query verification is pending. Remaining gates include crash injection, adversarial consensus tests, state sync/snapshots, multi-host validators, and independent security review.
