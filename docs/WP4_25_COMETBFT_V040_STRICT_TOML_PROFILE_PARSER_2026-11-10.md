# WP4.25 — CometBFT v0.40.0 Strict TOML Profile Parser

**Date:** 2026-11-10  
**Status:** Initial parser boundary implemented on a feature branch; CI pending  
**Pinned source:** `0880b4d378f347ab16e54ec677ff50d803f37d62`  
**Security disposition:** Not production-ready; does not close Station 2.

## Implemented in this change

- Strict UTF-8 byte input, BOM rejection, and a 1 MiB input ceiling.
- Python 3.12 TOML parsing; duplicate keys/tables and malformed TOML fail closed through `tomllib`.
- Exact field allow-list and exact Python value-type checks supplied by a source-pinned schema.
- Explicit defaults only; no host, environment, filesystem, or implicit runtime defaults are consulted.
- Safe integer subset and rejection of floating-point and TOML date/time values.
- Separation of `shared`, `node_local`, and `software` field scopes.
- Domain-separated digest over the shared projection; node-local values do not affect that projection.
- The parser refuses operation unless the caller supplies a schema marked complete and pinned to the reviewed source commit.

## Critical limitation

This PR does **not** ship the complete generated field inventory/default map for every CometBFT v0.40.0 config field. The test schema is deliberately synthetic and only proves parser behavior. A caller-supplied `complete=True` flag is an assertion by the schema provider, not proof that the inventory is complete.

Therefore this change must not be wired into the VSP production verifier or used to claim an actual CometBFT runtime profile digest until the complete schema is generated and independently checked against the pinned Go structs, TOML template, defaults, and validation methods. In particular, fields nested under experimental/libp2p sections and array-of-table values require full inventory coverage.

The canonical serializer admits only strings, booleans, safe integers, arrays, and objects. Its output must still be cross-checked against the repository's independent RFC 8785 implementation and golden vectors before using the digest as a VSP identity.

## Tests

The added tests cover duplicate-key rejection, unknown/mistyped fields, BOM/invalid UTF-8/oversize input, incomplete or wrong-source schema refusal, integer/bool confusion, and separation of node-local from shared digest inputs.

## Remaining work

1. Generate the full typed schema/default inventory from the exact pinned CometBFT source and its config template; do not handwave missing fields.
2. Cross-check every field's type, default, validation and scope, including nested and array-of-table settings.
3. Add golden vectors and independent RFC 8785 comparison for the profile projection.
4. Feed the computed digest into VSP verification from the same trusted startup path.
5. Add negative integration tests proving malformed/unknown config and local-policy drift cannot bypass the startup gate.

**Disposition:** Initial strict parser mechanism only. No full-profile digest claim, no trust-manifest activation, no production approval, and no Station 2 closure.


## WP4.26 — Initial Trust Manifest Bootstrap Verifier

The same feature branch now also contains an offline, fail-closed bootstrap verifier in `hnd_v02/trust_manifest.py`, with synthetic tests in `tests/test_trust_manifest.py` and a dedicated CI step.

Implemented checks:
- Exact manifest schema, strict UTF-8, duplicate JSON member rejection, canonical JCS bytes, and bounded input.
- Initial-only sequence 0 and null predecessor; fixed 2-of-3 policy and exactly three distinct Ed25519 governance identities.
- Governance key IDs recomputed from public keys and a domain-separated proof-of-possession challenge bound to chain, HND Genesis, CometBFT Genesis, nonce, key ID and role.
- Two distinct witness signatures over a domain-separated digest of the manifest core.
- Witness public keys are supplied as external trusted inputs; keys embedded in the manifest cannot establish their own trust.
- Exact comparison against externally supplied chain ID, HND Genesis digest, CometBFT Genesis digest and pinned CometBFT source commit.

This remains an offline verifier prototype. It does not establish that the external witness keys were provisioned through a real witnessed ceremony, prove human/custody independence, persist or pin the trust root, implement manifest rotation, connect to VSP startup verification, or enforce validator acknowledgements. Synthetic keys are generated only inside tests.

**Acceptance boundary:** this implementation validates a candidate sequence-zero trust-manifest object only. It is not production bootstrap approval and does not close Station 2.


## WP4.27 — Unanimous Operator Acknowledgement Verifier

Added `hnd_v02/operator_ack.py` and `tests/test_operator_ack.py`, wired into CI.

The offline verifier requires exactly one valid Ed25519 acknowledgement from every operator in an externally supplied expected-operator key set. Each acknowledgement binds the chain ID, exact VSP digest, activation height, operator ID and nonce. Missing, extra, duplicate, wrong-profile, wrong-height, non-canonical or invalidly signed acknowledgements fail closed. The result includes a digest of the verified acknowledgement set.

This is a pure verification function only. It does not establish operator independence, collect acknowledgements from real operators, store them durably, coordinate a rollout, atomically activate a profile, or prevent a process from bypassing the verifier. Those require deployment integration and independent operational evidence.


## WP4.28 — Trust Manifest → VSP Authorization Composition

Added `verify_vsp_with_trust_manifest` and an integration test proving that the governance public keys accepted for VSP signature verification are taken from the independently witness-validated manifest, rather than from a separately supplied arbitrary key map.

This is still a pure/offline composition. It does not persist the trust-manifest digest as the node's pinned trust root, provide trusted witness-key provisioning, or gate CometBFT/remote-signer startup.
