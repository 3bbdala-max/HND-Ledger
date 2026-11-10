# WP4.21 — VSP Strict Envelope and JCS Boundary

**Date:** 2026-11-10  
**Change type:** Isolated parser/canonicalization implementation  
**Status:** Implemented on feature branch; CI evidence pending  
**Security disposition:** NOT a complete VSP verifier; NOT approved for production.

## Scope

This work package adds a side-effect-free VSP envelope parser and the exact domain-separated payload digest/signature-message helpers. It does not load a trust manifest, verify Ed25519 signatures, validate the complete VSP payload schema, persist either monotonic counter, inspect or launch CometBFT, start HND, or authorize signing.

The implementation uses the already isolated, hash-pinned `rfc8785==0.1.4` spike dependency. It does not add that candidate to production `requirements.txt`. The existing HND transaction/Genesis canonical JSON format is untouched.

## Enforced boundary

- strict UTF-8 and no BOM;
- duplicate object member rejection before dictionary construction;
- unsigned integer tokens only, bounded by 2^53−1; floats, exponents, negative and unsafe integer tokens fail closed;
- bounded input size, nesting depth, node count, array size and string length;
- rejection of unpaired Unicode surrogates;
- exact top-level envelope members `payload` and `signatures`;
- two or three distinct, ordered Ed25519 signature records, with canonical Base64 and exact 64-byte signature width;
- exact RFC 8785 JCS byte equality for the complete envelope;
- payload digest `SHA-256("HND-VSP-v1" || 0x00 || JCS(payload))`;
- signature message `"HND-VSP-AUTH-v1" || 0x00 || raw_digest`.

## Test boundary

The new tests cover canonical acceptance, duplicate nested members, noncanonical envelope bytes, BOM/invalid UTF-8, invalid numeric tokens, duplicate signers, signature width, signature order, unknown envelope fields and digest domain separation.

The tests use synthetic zero-filled signature bytes solely to test envelope framing. They do not assert cryptographic validity. Cross-language JCS comparison remains a separate CI step and is not a substitute for the complete RFC 8785 conformance corpus or an independent security review.

## Remaining gates

1. Complete the full payload schema, including the approved CometBFT profile digest and the four separate identity layers.
2. Generate independently cross-checked RFC 8785 and VSP golden vectors.
3. Implement trust-manifest bootstrap, key-ID derivation and 2-of-3 Ed25519 verification.
4. Implement independent durable trust-manifest and profile anti-rollback anchors.
5. Bind the exact CometBFT Genesis, full version-specific runtime profile, binary/source identity and local validator identity.
6. Implement all-operator activation acknowledgements and witnessed recovery policy.
7. Enforce an unavoidable pre-start gate, OS/service bypass denial and signer-side checks.
8. Validate across genuinely separate operator/host domains and obtain independent security review.

**Disposition:** parser work package only; no station completion or production readiness claim.
