---
id: OME-760
linear_url: https://linear.app/openmined/issue/OME-760/add-the-healthbench-worst30-engine-exam-per-item-gpt-54-judging
status: in_progress
type:
priority: P1
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-06
closed:
---

# OME-760 — Add the healthbench-worst30 engine exam (per-item GPT-5.4 judging, unclipped mean)

Engine half of `OME-759`: `apps/url4-cloud/src/url4_cloud/benchmarks/healthbench/` on a
branch off `integration/keelan-all-changes-20260806`.

- prepare.py bakes ALL 525 Professional rows (pinned HF rev, pinned deps, preparer
  version in REVISION); cases public as chat envelopes, rubrics private.
- Variants `healthbench-worst30` (157 via `case_ids`) + `healthbench-smoke` (1 case).
- Per-rubric-item GPT-5.4 judging, byte-congruent grader prompt (empty intent = no
  system message), bounded retry then loud row failure, unclipped mean +
  verdict_coverage.
- Inherited review obligations: B1 loud missing-asset failure, B5 pinned deps,
  S-DR1 sample stdev, S-DR3 install-time preflight, S-RT1 expression size measured.

Ledger: `docs/work/2026-08-06-OME-760-healthbench-worst30-engine-exam.md`
Spec: `docs/spec/2026-08-06-OME-760-healthbench-worst30-spec.md`
Plan: `docs/plan/2026-08-06-OME-760-healthbench-worst30-plan.md`
