---
id: OME-538
linear_url: https://linear.app/openmined/issue/OME-538
status: Backlog
type: Refactor
priority: P2
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: collapse the dual text/AST compile pipelines

Two parallel implementations of the same group semantics (text path and AST path), each with its own laziness rules, bare-group rejection, inline-collection detection and intent folding. LoweringRegistry — the documented extension point — covers only the AST half, so a custom lowering silently does not apply to a text-path group segment. Direction: laziness becomes a property of a node; the grammar emits a deferred-group AST node and the compiler lowers AST only. Highest-risk item in the epic.

Spec → plan → owner approval before code. Under OME-537.
