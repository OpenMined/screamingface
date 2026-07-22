---
id: OME-542
linear_url: https://linear.app/openmined/issue/OME-542
status: Backlog
type: Refactor
priority: P2
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: compile iteration bodies once, not via surface text

MapNode._row and ReduceNode.resolve round-trip structure through surface text at execution time. This round-trip is the sole reason the _ITEM_KEY NUL-prefix hack exists, and any body form that does not survive re-parse is silently unrepresentable. Schedule after OME-538 and re-scope.

Spec → plan → owner approval before code. Under OME-537.
