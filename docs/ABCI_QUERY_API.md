# HND read-only ABCI Query API

Status: implemented, unit-tested, and exercised through CometBFT RPC on all three validators in run 42360521298.

## Constraints

- Read-only; never mutates balances, nonces, blocks, or mempool.
- Supports latest state only: request height 0 or the current committed height.
- prove must be false. Merkle proofs and historical queries are not implemented.
- Unknown paths and invalid account IDs return a nonzero ABCI Query code.
- Response value is UTF-8 JSON bytes carried in the ABCI byte field.

## Paths

### /hnd/v1/account

Pass exactly 32 raw account-ID bytes in RequestQuery.data.

Value fields:
- account_id: lowercase hex account ID.
- balance: integer in smallest HND units.
- next_nonce: next accepted transaction nonce.
- height: current committed application height.

An unknown but correctly sized account ID returns zero balance and nonce.

### /hnd/v1/info

Request data must be empty.

Value fields:
- chain_id
- height
- state_commitment: lowercase hex app state commitment.
- supply_cap
- total_supply
- account_count

## CometBFT RPC example

The RPC URI parser expects JSON-encoded strings for string arguments. The byte parameter uses CometBFT HexBytes form: 0x followed by hex, without JSON/base64 encoding.

Example parameter values:
- path="/hnd/v1/account"
- data=0x followed by the 64-character account ID
- height=0
- prove=false

For ledger metadata, omit data and set path="/hnd/v1/info".

The three-validator workflow verified account and ledger-info queries on all three nodes after a signed transfer. This is an internal local query surface, not a public account API or explorer. Do not expose CometBFT RPC publicly without a separate security design.
