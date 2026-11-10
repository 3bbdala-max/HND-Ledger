# WP4.22 — VSP v1 Payload, Governance Signature and Genesis Verifier

Date: 2026-11-10. Implemented on a dependent feature branch; CI evidence pending.

## Implemented
- Exact payload field sets based on the consolidated VSP candidate.
- The ratified HND and CometBFT Genesis bindings, plus the full CometBFT runtime profile digest, are required and compared with independently supplied expected context.
- Strict checks for chain identity, Genesis digests, CometBFT source and binary identity, sequence/predecessor, activation, validator records, governance policy and change metadata.
- Governance key IDs are recomputed from raw Ed25519 public keys using the HND-GOV-KEY-v1 domain separator.
- All supplied Ed25519 signatures must verify over the exact HND-VSP-AUTH-v1 message; at least two distinct enrolled keys are required.
- CometBFT v0.40.0 Ed25519 address derivation and exact VSP-to-Genesis roster comparison by public key, address and voting power.
- Stateless sequence and predecessor checks against an independently supplied active-profile record.

## Schema reconciliation
The approved VSP decisions require HND and CometBFT Genesis digests and the full CometBFT runtime profile identity. The earlier consolidated candidate's CometBFT object did not include the latter two bindings. This implementation adds required genesis_sha256 and profile_sha256 fields, both checked against independently provisioned context.

The candidate also states a general JSON integer ceiling of 2^53-1 and a larger CometBFT total voting-power ceiling. Those values conflict. This implementation applies the stricter 2^53-1 ceiling to all VSP JSON integer values; a future normative revision should state that effective bound explicitly.

## Not implemented
- Trust-manifest wire parser, bootstrap/enrollment ceremony or durable trust-root storage.
- Durable anti-rollback storage or crash-safe atomic activation.
- CometBFT TOML parser/normalizer and computation of the full typed runtime profile digest; this verifier requires the expected digest from a trusted caller.
- Binary provenance attestation beyond comparing values supplied by trusted context.
- Operator independence verification, operator acknowledgement, activation writes, startup gate, direct-binary bypass prevention or signer-side enforcement.
- Catastrophic governance-key loss recovery and independent security review.

Tests use ephemeral synthetic Ed25519 keys. No production keys or live validator identities are used.
