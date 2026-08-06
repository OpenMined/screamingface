---
ticket: OME-712
stack: repo
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-712 — Certify and decompose the benchmark runtime landing

## Intent

Certify the existing `OME-712-benchmark-runtime` branch against the live work item, repository
standards, and executable stack gates, then turn its cross-stack diff into an explicit sequence of
reviewable landing proposals. This unit changes decision records only: it does not alter production
code, prior tests, GitHub state, or Linear state.

## Planned changes

- `docs/tasks/2026-08-04-ome-712-benchmark-runtime.md`
- `docs/spec/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/plan/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/work/2026-08-04-OME-712-benchmark-runtime-certification.md`

## Test plan

- Pin `origin/main...origin/OME-712-benchmark-runtime` and inventory every commit and changed file.
- Run the canonical `url4`, `aigateway`, and `url4-cloud` gate lists without modifying prior tests.
- Compare the diff separately against repository standards and the live `OME-712` acceptance
  contract.
- Verify that every proposed landing has one owning stack, one observable acceptance boundary, and
  no hidden dependency on another proposed landing.

## Acceptance

- The live issue, repository mirror, specification, plan, and ledger form one traceable chain.
- Every changed file and commit is classified by owner and proposed landing.
- Gate results, untested claims, append-only exceptions, and live-test evidence are recorded without
  overstating readiness.
- The plan identifies the smallest safe bottom-up landing order and the Linear changes that would be
  required, while making no external mutations.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `docs/tasks/2026-08-04-ome-712-benchmark-runtime.md`
  - `docs/spec/2026-08-04-OME-712-benchmark-runtime-certification.md`
  - `docs/plan/2026-08-04-OME-712-benchmark-runtime-certification.md`
  - `docs/work/2026-08-04-OME-712-benchmark-runtime-certification.md`
- **Commits:** none; the four certification files remain untracked for owner review.
- **Gates:**
  - url4-cloud: Ruff, format, Pyright, layering, and coverage green; 771 passed, 10 skipped,
    129 warnings.
  - URL4: Ruff, format, Pyright, and 97.48% coverage green; 1,115 passed, 1 failed. The failure
    assumes Linux's single-argument size limit and does not reproduce on macOS, where the payload
    reached argv successfully.
  - AI Gateway: Ruff, format, Pyright, no-enterprise, and 92.48% coverage green; 2,664 passed,
    40 skipped, 1 failed. The unknown-user/wrong-password timing-ratio assertion also failed when
    rerun alone. The full suite used a raised macOS file-descriptor limit (`ulimit -n 10240`).
  - Per-file whitespace check: green for all four untracked certification artifacts.
- **Deviations:**
  - No production code or prior test was changed, and no branch was rebased or merged.
  - No push, PR/body/label mutation, Linear mutation, merge, or paid provider call was made.
  - Helm was not installed locally, so the real Helm render tests skipped; their GitHub check was
    green at the stale PR head.
  - Behavioral gates were separated from the append-only audit because `run_gates.py` defaults its
    comparison to `HEAD`; the cumulative branch was audited against the fixed merge base instead.

## Review evidence

- Fixed range: `e39f9fbaec4827fe41a3bb9bd924e40b2e7eb2d2..b2c64433c34e12982dfbdcd19ac2664dc975f846`.
- Current-main comparison: `563c905f8dc815df81afa753cfaf2b587c4e4f8c`; source is 36 commits ahead
  and 36 behind.
- PR shape: 112 files, 11,669 additions, 263 deletions, 36 commits; draft with no status label.
- Commit audit: all subjects are conventional; 24 of 36 bodies omit `Refs: OME-N`; the last commit
  changes 76 files, adds 4,981 lines, deletes 1,919, and has an empty body.
- Append-only audit: 12 pre-existing test modules are modified relative to the merge base. The final
  commit also removes four tests and two implementation modules added earlier in the same cycle.
- CI audit: PR workflows do not build `Dockerfile.benchmark`; the dev Benchmark-image job publishes
  only to GHCR even though the dev base image also publishes to ACR. Release is consistently
  GHCR-only and has no registry-parity gap.
- Reproducibility audit: the Benchmark image uses a floating uv build image and installs
  `datasets>=2.19` outside `apps/url4-cloud/uv.lock`.
- Primary protocol check: [arXiv:2602.11685](https://arxiv.org/abs/2602.11685) specifies five
  independent grading runs for 100 tasks and an average 39.3 criteria per task. The code's five-pass
  constant is correct; Linear's three-pass progress text is stale.

## Confirmed blockers

1. Empty Aggregation produces a successful zero-Case result; existing tests explicitly require it.
2. Candidate evaluation shares the node that exposes Benchmark task/verdict/aggregate routes. A
   deterministic in-memory probe retrieved a synthetic private criterion requirement.
3. With shipped outbound configuration, Candidate URL4 can fetch an absolute URL without passing
   through Gateway/Tavily exclusion policy. A deterministic in-memory probe retrieved a synthetic
   answer-key URL.
4. Helm derives an ACR Benchmark image path for dev, but the dev Benchmark-image job does not
   publish it.
5. Linear records no correct hand-checked deployed score, and paid acceptance has not been approved.
6. The source branch is stale against current `main`; final workflow and platform gates are unknown.

## Proposed next decision

Ask the owner to approve the convergence scope and partial-result contract first. Then fix the
fail-closed and Candidate-capability blockers in focused local work, add registry/PR-build coverage,
and only then reconstruct the nine proposed landings from current `main`. External issue/PR changes
and paid acceptance remain separate approval points.

## Local remediation after certification

- Zero-Case Aggregation now raises `AggregateError("aggregation scored no Cases")`; the installed
  route exposes the existing permanent `benchmark_unavailable` error.
- The confidence-gate exception reverses exactly two prior tests that asserted empty Aggregation was
  successful. One new installed-route test and one all-invalid-row boundary test were added.
- url4-cloud canonical gate: all green with append-only explicitly skipped for those two approved
  reversals; 773 passed, 10 skipped, 94.07% coverage, 129 warnings.
- The dev Benchmark-image job now uses the existing Azure OIDC identity and publishes the same
  immutable build to both GHCR and ACR. A workflow-contract test pins registry parity.
- After both local fixes, url4-cloud remains all green: 774 passed, 10 skipped, 94.07% coverage,
  129 warnings. The patch remains local and uncommitted.
