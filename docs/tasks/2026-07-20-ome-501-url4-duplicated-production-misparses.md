---
id: OME-501
linear_url: https://linear.app/openmined/issue/OME-501
status: Done
type: Bug
priority: P1
labels: [url4-engine, pkg/url4-python-sdk, autonomous, agentic]
created: 2026-07-20
closed: 2026-07-20
---

# OME-501 — Silent mis-parses from duplicated productions

Three bugs sharing one root cause: a production implemented or enforced twice, only one copy correct. (A) decode_envelope splits intent before scanning for `*(`, destroying intent-bearing collections. (B) nested query-param split is not paren-depth aware. (C) resume/rid transport params filtered on ingress but leak from expression text.

Parent epic: `OME-500`. Full audit findings live in the Linear description.
