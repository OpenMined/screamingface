---
id: OME-535
linear_url: https://linear.app/openmined/issue/OME-535/url4-abnf-conformance-resolve-call-context-source-lists-caller-side
status: Done
type: Feature
priority: P2
labels: [url4-engine, autonomous, agentic]
created: 2026-07-21
closed: 2026-07-21
---

# url4: ABNF conformance — caller-resolved call contexts (patch 2/2)

A relative call's parens now parse as a source-list, resolved caller-side
and dispatched packed — nested calls in call parens finally execute.
Remote q= stays an expression the remote evaluates; `@`-bearing and
unparseable contexts fall back verbatim (holdings pass-through + prose
compatibility). Under OME-500.

See `docs/work/2026-07-21-OME-535-call-context-source-lists.md`.
