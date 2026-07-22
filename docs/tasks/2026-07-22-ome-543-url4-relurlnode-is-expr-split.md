---
id: OME-543
linear_url: https://linear.app/openmined/issue/OME-543
status: Backlog
type: Refactor
priority: P3
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: split RelUrlNode on its is_expr mode flag

One class, two unrelated behaviours; half the fields meaningless in the data-read mode. 'Is this a dispatchable call?' is spelled isinstance(x, RelUrlNode) and x.is_expr in four compiler sites. Also covers _push_label mutating already-lowered nodes and _fanout_call unwrapping the built graph to recover a label the slot already knew.

Spec → plan → owner approval before code. Under OME-537.
