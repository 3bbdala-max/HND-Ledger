# WP4.14 — JCS compatibility spike CI evidence (2026-11-07)

## Result

The isolated JCS compatibility spike and the repository CI workflow completed successfully on:

- Branch: `phase-0.2-planning`
- Commit: `df07db3648ff7e4eb6df9505ec686c24f3d02812`
- GitHub Actions run: `42322613408`
- Run conclusion: `success`
- Updated at: `2026-11-07T01:15:21Z`

Both jobs completed successfully:

- `hnd-v02-tests`
- `cometbft-single-node-smoke`

The HND test job includes 221 existing HND tests and the five-test isolated JCS compatibility suite. The latter checks canonical byte vectors, UTF-16 property ordering, negative zero and number serialization, strict JSON rejection cases, and byte-for-byte comparison between Python `rfc8785==0.1.4` and JavaScript `canonicalize@2.1.0`.

## Dependency integrity scope

The Python spike dependency is pinned and installed with a recorded wheel SHA-256 in `requirements-vsp-jcs-spike.txt`. The JavaScript comparator is pinned to exact version `canonicalize@2.1.0` in the workflow, but this spike does not yet provide an npm lockfile or independently verified npm package integrity. Therefore this is not a complete supply-chain lock or provenance claim.

## Explicit limitations

This result validates only an isolated compatibility experiment and its CI execution. It does **not**:

- freeze, approve, or ratify the VSP normative specification;
- integrate JCS into consensus-critical runtime paths;
- establish governance trust roots or validate real governance signatures;
- authorize production keys, validators, signing infrastructure, token issuance, or deployment;
- close the previously documented distributed single-writer, mandatory remote-signer, transport-authentication, anti-rollback, recovery, or operational-control gates.

No production readiness or release approval is implied.
