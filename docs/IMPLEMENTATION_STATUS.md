# HND v0.2 implementation status

**Status:** Python deterministic ledger integrated with a pinned CometBFT v0.40.0 local consensus engine and tested in controlled CI; not production-ready.

## Implemented in this branch

- Python package targeting Python 3.11+.
- Ed25519 transaction signing and verification; sender identity bound to the public key.
- Canonical CBOR transaction serialization and strict re-encoding validation.
- Domain-separated account identifiers, signing messages, transaction IDs, genesis identifiers, block identifiers, and state commitments.
- Chain-ID binding, uint64 amount and nonce validation, self-transfer rejection, sequential nonces, insufficient-funds rejection, overflow protection, and supply-cap invariant.
- Deterministic blocks with sequential heights, parent hashes, exact transaction bytes, and state roots.
- SQLite persistence and restart recovery by replaying committed blocks from the genesis snapshot.
- State commitment v3 includes chain ID and supply cap as well as account balances and nonces. Pre-v3 local state roots are incompatible.
- Funded genesis accepts a bounded canonical JSON envelope containing a Base64 canonical-CBOR allocation payload. Genesis state and CometBFT genesis marker are persisted in one SQLite transaction.
- ABCI++ lifecycle methods for Info, InitChain, CheckTx, InsertTx, ReapTxs, PrepareProposal, ProcessProposal, FinalizeBlock, and Commit.
- Bounded private JSONL IPC over a Unix-domain socket; strict envelope validation, duplicate-key rejection, 1 MiB frame limit, and socket mode 0600.
- Go CometBFT socket adapter pinned to v0.40.0. The Go layer is a transport adapter; Python remains the reference state machine.
- Go IPC client handles partial writes and validates response framing and request correlation.
- Go ABCI listener rejects non-loopback addresses.
- CI workflows for Python tests, Go tests/static analysis, one-node restart integration, and three-validator signed-transfer integration.

## Verified integration scope

On commit `1c62d3cad548315b8cecb811edd76ee6b93808af`:

- Python tests: run [42359852666](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852666), success.
- Go adapter tests and static analysis: run [42359852685](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852685), success.
- One-node CometBFT block production and restart recovery: run [42359852690](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852690), success.
- Three-validator funded-genesis and signed-transfer integration: run [42359852656](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42359852656), success.

The three-validator workflow uses three independent node homes, validator identities, Python processes, SQLite databases, and IPC sockets. It commits one signed transfer at height 4, checks the sender and recipient balances and sender nonce on all nodes, compares state commitments, checks the CometBFT header app hash at height 5, restarts validator 0, and rechecks its persisted transfer, balances, nonce, and the common app hash.

## Design decisions

- CometBFT v0.40.0 is the selected engine for the controlled local integration. This is not a production deployment approval.
- CometBFT handles peer communication, validator voting, and block consensus; the Python engine validates HND transactions and computes deterministic state.
- The Go adapter is intentionally thin and communicates with Python through a private Unix socket.
- Only Commit writes the finalized block to the HND SQLite ledger.
- The Go ABCI listener is restricted to loopback interfaces; it is not a public ABCI endpoint.

## Not implemented or not independently validated

- Wallet software, private-key custody, key recovery, rotation, and revocation.
- Public account API, explorer, public RPC service, and user-facing transaction submission.
- Production genesis allocation policy, issuance governance, mint/burn policy, or real-value token distribution.
- Validator admission, voting-power governance, validator-set changes, operator key management, slashing, or rewards.
- ABCI Query, snapshots, state sync, and vote-extension methods; unsupported methods fail closed.
- Multi-host and multi-operator deployment, network partitions, message loss/reordering, equivocation, Byzantine proposer behavior, and adversarial load.
- Crash-injection campaign across every FinalizeBlock/Commit boundary; backup, restore, and database migration procedures.
- Independent protocol, cryptographic, application security, economic, and legal review.

## Release gate

No public deployment, issuance, or real-value use should occur until the missing implementation work is complete, a documented consensus threat model is tested under adversarial conditions, and independent security and legal reviews are completed.
