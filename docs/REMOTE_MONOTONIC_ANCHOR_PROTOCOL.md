# HND Remote Monotonic Anchor Protocol v1

**Status:** implementation contract and client reference; no production anchor service is supplied by this repository.

## Security objective

Keep accepted Trust Manifest, VSP, and activation-witness checkpoint state outside the validator and witness-cluster rollback domains. Restoring an old local disk, SQLite backup, VM snapshot, or application image must not restore the remote anchor to an earlier value.

The service must be independently administered and independently recoverable from the HND validator host. A remote URL alone is not independence. A service backed by a database snapshot that an attacker can roll back together with the validator host does not meet this objective.

## Transport and identity

- HTTPS only; TLS 1.2 minimum; normal certificate-chain and hostname validation are mandatory.
- Mutual TLS is mandatory. The client presents a provisioned client certificate; the service authenticates and authorizes that identity.
- The endpoint must be configured out-of-band by deployment policy. Redirects are rejected.
- The client sends no bearer token, private signing key, or secret in the request body.
- Client certificate issuance, rotation, revocation, CA custody, endpoint DNS, and service operator identity require a separate documented ceremony.
- Fail closed on TLS errors, timeout, non-200 response, unexpected content type, oversized response, malformed JSON, duplicate JSON keys, or an unknown response shape.

## Role-based client authorization

The reference server requires an explicit `AnchorClientRegistry`; a certificate fingerprint allow-list alone is not authorization. The registry maps each SHA-256 certificate fingerprint to an immutable principal ID, role, exact namespace set, and operation set. The server resolves this policy for every request and checks both route and namespace before touching anchor state.

Supported v1 roles are deliberately constrained:

| Role | Namespace scope | Read | Compare-and-advance |
|---|---|---:|---:|
| `witness` | `activation-witness` only | Yes | Yes |
| `trust-manifest-authority` | `trust-manifest` only | Yes | Yes |
| `vsp-profile-authority` | `vsp-profile` only | Yes | Yes |
| `finalizer` | Explicit subset of all namespaces | Yes | No |
| `recovery` | No v1 namespace | No | No |
| `operator` | No v1 namespace | No | No |

A witness certificate cannot read or advance trust-manifest or VSP state. A finalizer is read-only. Recovery and operator identities receive no authority through the v1 API because no dedicated recovery operation exists; they cannot use compare-and-advance as a substitute recovery route.

The registry supports live revocation by removing a fingerprint and atomic certificate rotation by replacing the old fingerprint with the new one and its policy. Deployments must keep registry updates under a separately controlled certificate-administration process. Rotation must not broaden the principal's role or namespace scope. Unknown, revoked, cross-role, and cross-namespace requests fail closed with HTTP 403. The registry is an in-process reference control; production must persist and audit authorization changes in a separately governed control plane.

## API

All requests are UTF-8 JSON POSTs. Responses are UTF-8 JSON with Content-Type application/json. The client currently accepts at most 16 KiB per response.

### Read state

POST /v1/state/read

Request:

```json
{"namespace":"trust-manifest"}
```

Response when uninitialized:

```json
{"record":null}
```

Response when initialized:

```json
{"record":{"sequence":0,"digest":"<64 lowercase hexadecimal characters>"}}
```

Allowed namespaces are exactly trust-manifest, vsp-profile, and activation-witness.

### Compare and advance

POST /v1/state/compare-and-advance

Request:

```json
{
  "namespace":"trust-manifest",
  "expected_current":null,
  "new_record":{"sequence":0,"digest":"<64 lowercase hexadecimal characters>"}
}
```

For an initialized namespace, expected_current is the exact record returned by the preceding read. new_record is the proposed successor.

Response:

```json
{"advanced":true}
```

advanced:false means the current state did not equal expected_current; callers must treat this as a conflict and must not launch or activate. The server must never silently overwrite a different current record.

## Mandatory server-side invariants

The service implementation MUST provide all of the following, not merely rely on client checks:

1. Linearizable compare-and-advance across all service replicas and regions.
2. Durable commit before returning advanced:true.
3. Exact bootstrap values: trust-manifest starts at sequence 0; vsp-profile starts at sequence 1; activation-witness starts at sequence 0.
4. Thereafter, only current.sequence + 1 is accepted. No replay, skip, reset, delete, namespace recreation, or digest replacement at the same sequence.
5. expected_current must match both sequence and digest exactly; concurrent writers must have one winner.
6. A committed record cannot be rolled back by an ordinary service database restore, operator console, backup restore, or disaster-recovery procedure. Recovery must preserve the highest committed record or require a separately witnessed recovery ceremony that does not silently lower sequence.
7. Every write is attributable to an authenticated principal and produces an append-only audit event containing namespace, old record, new record, principal, request ID, and commit time. Do not log client private keys or TLS secrets.
8. Service administrators, backup administrators, and HND validator operators must not all be the same principal or share a single credential/failure domain.
9. Read-after-write consistency is mandatory. A successful advance must be visible to every subsequent read.
10. The service must be monitored; inability to read or advance is a hard startup/activation failure.

## Witness checkpoint digest and crash-recovery protocol

The `activation-witness` namespace protects the receipt-log checkpoint, not merely a free-running counter. The witness implementation MUST use a deterministic, domain-separated digest chain.

Genesis checkpoint:

```text
genesis_digest = SHA256(
  "HND-STATION2-WITNESS-GENESIS-V1\\0" ||
  canonical_json({schema, witness_id, config_epoch})
)
```

For each receipt at counter `n + 1`:

```text
checkpoint_digest = SHA256(
  "HND-STATION2-WITNESS-CHECKPOINT-V1\\0" ||
  canonical_json({
    schema,
    witness_id,
    config_epoch,
    counter,
    previous_checkpoint_digest,
    activation_id,
    activation_digest,
    receipt_sha256
  })
)
```

Canonical JSON is UTF-8, sorted keys, no insignificant whitespace, ASCII-safe strings, and rejects non-finite values. `receipt_sha256` is SHA-256 over the exact canonical receipt bytes, including the Ed25519 signature. The anchor sequence equals the committed witness counter. Sequence 0 is the genesis checkpoint; the first receipt advances it to sequence 1.

### Required write protocol

The witness quorum store and independent anchor cannot participate in one atomic transaction. The implementation MUST therefore use a single serialized pending operation and explicit reconciliation:

1. Read the quorum-committed witness counter/checkpoint and the independent anchor. Require exact equality. On first bootstrap only, initialize both at counter 0 with the same deterministic genesis digest. Never initialize an empty anchor if the witness store already contains receipt history.
2. For a new activation, create one immutable pending record in a durable quorum transaction. It contains the exact activation ID/digest, proposed counter, signed receipt, previous checkpoint digest, and proposed checkpoint digest. The transaction compares the current counter and requires the pending slot to be absent.
3. Advance the independent anchor from the exact previous record to the proposed counter/checkpoint digest using linearizable compare-and-advance.
4. Finalize in a second quorum transaction: compare the exact pending record and previous counter, write the immutable receipt, advance the committed counter/checkpoint, and remove the pending slot.
5. Return the receipt only after finalization is confirmed by a linearizable read.

### Crash and ambiguity reconciliation

- If the anchor is still at the previous counter and the exact pending record exists, retry the same anchor compare-and-advance.
- If the anchor is already at the pending counter and its digest exactly matches the pending record, finalize that same pending record.
- If the witness store is at the anchor counter and the checkpoint digests match, the operation is committed; return the stored original receipt for a retry.
- If the anchor is ahead of the restored witness store, the pending record is missing, counters regress, or any digest differs, fail closed. Do not reset either counter or invent a replacement activation ID.
- A pending record for another activation must be reconciled before a new acknowledgement can be accepted. The implementation must not create two simultaneous pending records.
- A timeout after any write is an unknown outcome. The caller reconciles the same activation ID and digest.

This protocol makes a whole-cluster stale restore detectable only if the independent anchor itself remains outside the witness cluster's administrative, credential, and backup/restore failure domain. The protocol document and test doubles do not establish that deployment fact.

## Client reference

hnd_v02/remote_monotonic_anchor.py implements the client-side HTTPS/mTLS request and strict response boundary. tests/test_remote_monotonic_anchor.py uses an in-memory fake service to exercise the client contract; it does not prove a real service is deployed, independently administered, linearizable, or rollback-resistant.

The existing SQLiteMonotonicAnchor remains a single-host reference adapter only. It MUST NOT be configured as the production anti-rollback authority.

## Activation and witness integration still required

The activation transaction must use the remote anchor as the authoritative monotonic state and coordinate it with the local atomic profile activation. The activation-witness namespace is reserved for a digest-chained checkpoint of the witness receipt log; its sequence must track the committed witness counter. The anchor must be operated under separate administration and recovery credentials from the witness quorum. The implementation must define and test crash recovery for these cases:

- remote advance succeeds but local activation commit fails;
- local state is stale while remote state is ahead;
- request times out after the service commits but before the client receives the response;
- two nodes attempt the same transition concurrently;
- remote service is unavailable during startup;
- operator recovery after remote service disaster.

A timeout after a write is an unknown outcome, not permission to retry with a different successor. The client must read the remote state and reconcile exact sequence/digest before proceeding.

## Release gate

This protocol and client are not a production anti-rollback service. Station 2 remains open until a real independently operated service, server implementation, deployment identity/certificate ceremony, fault-injection tests, remote/local crash-recovery integration, and independent security review are complete.
