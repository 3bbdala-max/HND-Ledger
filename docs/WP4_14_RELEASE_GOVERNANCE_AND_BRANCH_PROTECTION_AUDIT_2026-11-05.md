# HND v0.2 — release governance and branch protection audit

**Date:** 2026-11-05  
**Branch reviewed:** `phase-0.2-planning`  
**Review type:** GitHub metadata and workflow review; documentation-only

## 1. Executive result

The repository currently has no published GitHub Releases in the queried release collection and no repository rulesets returned by the available API query. A direct branch-protection read for `main` returned HTTP 403 `Resource not accessible by integration`; therefore branch protection cannot be declared absent or present from this review.

The current workflow runs on pushes to `phase-0.2-planning` and pull requests targeting `main`. It does not declare pull-request validation for PRs targeting `phase-0.2-planning`.

The latest documentation commit triggered CI run `41978657337`. At the time of this review, `hnd-v02-tests` had completed successfully, while `cometbft-single-node-smoke` remained in progress. This run is therefore **not yet a completed green run** and must not be described as fully passed.

## 2. Verified repository metadata

- Repository: `3bbdala-max/HND-Ledger`
- Working branch: `phase-0.2-planning`
- Queried Releases collection: empty (`[]`)
- Queried repository rulesets collection: empty (`[]`)
- Queried `main` branch protection endpoint: inaccessible to this integration (403).

Interpretation:
- No published GitHub Release was returned by the query; this is not proof that no release artifacts exist elsewhere.
- No repository rulesets were returned by the query; branch protection may be configured through legacy branch-protection settings, which could not be read.
- The 403 is a permission limitation, not evidence that branch protection is disabled.

## 3. CI trigger and current run

The workflow `.github/workflows/hnd-v02-tests.yml` currently declares:
- `push` to `phase-0.2-planning`;
- `pull_request` targeting `main`.

It does not declare PR checks for the planning branch as a base branch.

Latest run inspected:
- Run ID: `41978657337`
- Commit: `3faf28cd968c3251c9399ad2eb0059f0256e5382`
- `hnd-v02-tests`: completed successfully.
- `cometbft-single-node-smoke`: in progress at inspection time.

The run must be rechecked after completion. Do not infer the second job's result from the first job's success.

## 4. Release governance controls not established

This review did not establish:
- required status checks and merge blocking on `main`;
- required pull-request reviews or CODEOWNERS enforcement;
- signed release tags or signed binaries;
- reproducible build attestation or provenance;
- SBOM generation/publication and dependency vulnerability policy;
- independent security sign-off and change approval;
- production deployment approval, rollback plan, or incident/key-compromise runbook;
- a published release artifact corresponding to a reviewed immutable commit.

These are open verification items, not all necessarily code defects. Repository owner/admin inspection is required for settings the integration cannot read.

## 5. Required next actions (not applied)

1. Have a repository administrator inspect `main` branch protection and confirm required checks, review count, stale-review dismissal, and admin bypass policy.
2. Decide whether `phase-0.2-planning` should also run PR-triggered CI; if so, add it as a PR base branch.
3. Recheck run `41978657337` and record the final result for both jobs.
4. Before a public production release, establish signed immutable tags, artifact provenance, SBOM, independent security approval, and a documented deployment/rollback process.
5. Keep the production launch gate closed until the anti-rollback and key-custody gaps in the related audits are addressed.

## 6. Disposition

**Release governance status: NOT VERIFIED / NOT APPROVED.**

No release or tag was created. No branch-protection or ruleset setting was changed. No workflow, source, or test file was modified. This report is a metadata/configuration audit only and is not a security certification or production launch approval.


## 7. Fresh branch metadata reconciliation — 2026-11-21

A fresh GitHub repository metadata read on 2026-11-21 returned the following for both
`main` and `phase-0.2-planning`:

| Branch | `protected` | `protection.enabled` | Required status checks |
|---|---:|---:|---|
| `main` | `false` | `false` | enforcement `off`; no contexts/checks |
| `phase-0.2-planning` | `false` | `false` | enforcement `off`; no contexts/checks |

The repository metadata identifies the repository as private and `main` as its default
branch. This fresh branch-object response supersedes the earlier uncertainty in §2 about
whether protection was enabled: the current API representation explicitly reports both
branches as unprotected. No branch setting was changed by this review.

### Required administrator action

- Protect `main` against direct pushes, force pushes, and deletion.
- Require pull requests and at least one independent review before merging.
- Require the relevant successful HND CI checks on the exact PR head; do not accept a
  job that never obtained a runner as a successful check.
- Dismiss stale approvals after new commits and require review conversations to be resolved.
- Decide explicitly whether `phase-0.2-planning` should be PR-only. Until that policy is
  chosen, preserve the current engineering workflow but prevent force-push and deletion.

The available repository connector exposes branch-protection reads but no branch-protection
write operation. These settings therefore remain an administrator-side dependency and are
tracked separately as issue #55. This audit does not claim that protection has been enabled.
