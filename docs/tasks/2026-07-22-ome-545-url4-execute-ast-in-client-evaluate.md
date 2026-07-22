---
id: OME-545
linear_url: https://linear.app/openmined/issue/OME-545
status: Backlog
type: Refactor
priority: P3
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: execute the AST in Client.evaluate

evaluate builds an AST, renders it, then run() parses it again, though run() accepts AstNode directly. Any AST the grammar cannot express becomes unexecutable rather than merely unloggable — the reason _passthrough uses the contrived (r:0:<call>)!'$r' idiom. Also the home for the render check= decision deferred from OME-536.

Spec → plan → owner approval before code. Under OME-537.
