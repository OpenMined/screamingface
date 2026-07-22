---
id: OME-540
linear_url: https://linear.app/openmined/issue/OME-540
status: Backlog
type: Refactor
priority: P3
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: accept protocol params structurally

peer/server._reassemble re-serializes already-structured params into surface text so decode_envelope can re-parse them. A value containing ';' or '=' corrupts the expression. Expression.params already exists as a first-class AST field.

Spec → plan → owner approval before code. Under OME-537.
