---
id: OME-504
linear_url: https://linear.app/openmined/issue/OME-504
status: Todo
type: Improvement
priority: P2
labels: [url4-engine, pkg/url4-python-sdk, autonomous, agentic]
created: 2026-07-20
closed:
---

# OME-504 — Character-class validation sweep

Over-permissiveness hardening. Python \w is Unicode-aware where ABNF means ASCII; annotation parsing validates structure but never charsets. No wrong behaviour today — the parser is a strict superset. Gated on OME-503.

Parent epic: `OME-500`. Full audit findings live in the Linear description.
