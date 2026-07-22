---
id: OME-541
linear_url: https://linear.app/openmined/issue/OME-541
status: Backlog
type: Refactor
priority: P3
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: give Url4Node route validation + identity registry

cli/_serve.py re-derives Url4Node._check_routable's collision rules, the reserved-path set, the grammar's private _IDENTITY_NAME_RE, and fetch_holdings' exact-then-default fallback — its own comments admit the mirroring. Drift shows up as 'config accepted, node fails at runtime'. Must preserve the fail-fast-before-bind property.

Spec → plan → owner approval before code. Under OME-537.
