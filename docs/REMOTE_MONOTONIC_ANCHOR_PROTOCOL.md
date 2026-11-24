# HND Remote Monotonic Anchor Protocol v1

**Status:** implementation contract and client reference; no production anchor service is supplied by this repository.

## Security objective

Keep the accepted Trust Manifest and VSP sequence/digest outside the validator host's rollback domain. Restoring an old local disk, SQLite backup, VM snapshot, or application image must not restore the remote anchor to an earlier value.

The service must be independently administered and independently recoverable from the HND validator host. A remote URL alone is not independence. A service backed by a database snapshot that an attacker can roll back together with the validator host does not meet this objective.

## Transport and identity

- HTTPS only; TLS 1.2 minimum; normal certificate-chain and hostname validation are mandatory.
- Mutual TLS is mandatory. The client presents a provisioned client certificate; the service authenticates and authorizes that identity.
- The endpoint must be configured out-of-band by deployment policy. Redirects are rejected.
- The client sends no bearer token, private signing key, or secret in the request body.
- Client certificate issuance, rotation, revocation, CA custody, endpoint DNS, and service operator identity require a separate documented ceremony.
- Fail closed on TLS errors, timeout, non-200 response, unexpected content type, oversized response, malformed JSON, duplicate JSON keys, or an unknown response shape.

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

Allowed namespaces are exactly trust-manifest, vsp-profile, and hrec-checkpoint. Bootstrap sequences are 0, 1, and 0 respectively. The hrec-checkpoint namespace stores the HREC chain checkpoint digest; its initial sequence-0 digest must be provisioned out-of-band from the independently verified HND genesis.

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
3. Exact bootstrap values: trust-manifest starts at sequence 0; vsp-profile starts at sequence 1; hrec-checkpoint starts at sequence 0 with an out-of-band pinned genesis digest.
4. Thereafter, only current.sequence + 1 is accepted. No replay, skip, reset, delete, namespace recreation, or digest replacement at the same sequence.
5. expected_current must match both sequence and digest exactly; concurrent writers must have one winner.
6. A committed record cannot be rolled back by an ordinary service database restore, operator console, backup restore, or disaster-recovery procedure. Recovery must preserve the highest committed record or require a separately witnessed recovery ceremony that does not silently lower sequence.
7. Every write is attributable to an authenticated principal and produces an append-only audit event containing namespace, old record, new record, principal, request ID, and commit time. Do not log client private keys or TLS secrets.
8. Service administrators, backup administrators, and HND validator operators must not all be the same principal or share a single credential/failure domain.
9. Read-after-write consistency is mandatory. A successful advance must be visible to every subsequent read.
10. The service must be monitored; inability to read or advance is a hard startup/activation failure.

## Client reference

hnd_v02/remote_monotonic_anchor.py implements the client-side HTTPS/mTLS request and strict response boundary. tests/test_remote_monotonic_anchor.py uses an in-memory fake service to exercise the client contract; it does not prove a real service is deployed, independently administered, linearizable, or rollback-resistant.

The existing SQLiteMonotonicAnchor remains a single-host reference adapter only. It MUST NOT be configured as the production anti-rollback authority.

## HREC checkpoint integration

The isolated HREC prototype adds the hrec-checkpoint namespace and a bridge in hnd_v02/hrec_checkpoint_anchor.py. The genesis digest must be provisioned through a separately witnessed ceremony. A block checkpoint is published only after the caller has independently confirmed durable HND and CometBFT commits. The bridge enforces exact predecessor sequence/digest and reconciles a lost compare-and-advance response by reading the exact proposed record. This bridge does not itself observe or prove either database commit, does not provide an independently operated service, and is not wired into the CometBFT commit path or mandatory startup gate.

## Activation integration still required

The activation transaction must use the remote anchor as the authoritative monotonic state and coordinate it with the local atomic profile activation. The implementation must define and test crash recovery for these cases:

- remote advance succeeds but local activation commit fails;
- local state is stale while remote state is ahead;
- request times out after the service commits but before the client receives the response;
- two nodes attempt the same transition concurrently;
- remote service is unavailable during startup;
- operator recovery after remote service disaster.

A timeout after a write is an unknown outcome, not permission to retry with a different successor. The client must read the remote state and reconcile exact sequence/digest before proceeding.

## Release gate

This protocol and client are not a production anti-rollback service. Station 2 remains open until a real independently operated service, server implementation, deployment identity/certificate ceremony, fault-injection tests, remote/local crash-recovery integration, and independent security review are complete.
