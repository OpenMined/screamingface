---
id: OME-503
linear_url: https://linear.app/openmined/issue/OME-503
status: Todo
type: Improvement
priority: P1
labels: [url4-engine, pkg/url4-python-sdk, autonomous, agentic]
created: 2026-07-20
closed:
---

# OME-503 — ABNF amendments for natural-language content

Four places where the grammar is wrong and the implementation is right: exec-value omits ':' needed by iteration.slice; bare-value cannot express NL; quoted-char forbids non-ASCII; $$ is described as lexing-phase but implemented at resolution. Gates OME-504.

Parent epic: `OME-500`. Full audit findings live in the Linear description.
