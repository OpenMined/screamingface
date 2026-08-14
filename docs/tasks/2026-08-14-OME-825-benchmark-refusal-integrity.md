---
id: OME-825
linear_url: https://linear.app/openmined/issue/OME-825/benchmark-failure-policy-follow-up-refusal-integrity-review-cleanups
status: In Progress
type: Bug
priority: P2
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-14
---

# Benchmark failure policy follow-up: refusal integrity + review cleanups from PR #584

Close the five confirmed findings from the adversarial review of PR #584 (OME-807):
two refusal-integrity bugs (null-text content-filter refusal published as a scored
plausible-zero; IFEval LANL selection laundering refusal prose into a scored output)
and three cleanups (outcome-triple validator duplicated across benchmark packages,
coverage formula duplicated producer/validator, dead `provider_refusal` clauses).

Spec: `docs/spec/2026-08-14-OME-825-benchmark-refusal-integrity.md`
Plan: `docs/plan/2026-08-14-OME-825-benchmark-refusal-integrity.md`
Ledger: `docs/work/2026-08-14-OME-825-benchmark-refusal-integrity.md`
