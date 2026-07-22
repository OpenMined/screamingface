---
id: OME-533
linear_url: https://linear.app/openmined/issue/OME-533/url4-canonical-relative-call-rejected-at-fragment-root-while-its-sugar
status: Backlog
type: Bug
priority: P2
labels: [url4-engine, autonomous, agentic]
created: 2026-07-21
closed:
---

# url4: canonical relative call rejected at fragment root while sugar parses

`/p(x)!'go'` parses; `/p?q=(x)!'go'` fails `missing_intent` — the top-level
`!`-split detaches the canonical call's own intent before the call production
sees it, and the remainder trips the OME-508 call check. §8.1 defines sugar BY
desugaring to canonical, so canonical must be accepted wherever sugar is.
Found verifying OME-530 (the decode fix let this shape reach the parser for
the first time). Under OME-500.
