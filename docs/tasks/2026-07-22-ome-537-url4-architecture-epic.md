---
id: OME-537
linear_url: https://linear.app/openmined/issue/OME-537
status: Backlog
type: Epic
priority: P3
labels: [url4-engine, autonomous, agentic]
created: 2026-07-22
closed:
---

# url4 architecture — mechanisms sitting at the wrong layer

Umbrella for the architectural findings from the package-wide url4 quality review
(OME-536, done). OME-536 applied the behaviour-preserving cleanups; everything under
this epic changes structure and in several cases behaviour, so each sub-issue runs
spec → plan → owner approval before code.

Sub-issues: OME-538 (dual compile pipelines), OME-539 (wire codec in core/),
OME-540 (structural protocol params), OME-541 (Url4Node route validation),
OME-542 (compile iteration bodies once), OME-543 (RelUrlNode is_expr split),
OME-544 (cross-run compile cache), OME-545 (execute AST in Client.evaluate),
OME-546 (duplicated ASGI helpers + aclose asymmetry).

OME-538, OME-539 and OME-542 are the substantial, interrelated ones — OME-542 partly
dissolves if OME-538 lands.
