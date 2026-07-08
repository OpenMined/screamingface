---
id: OME-367
linear_url: https://linear.app/openmined/issue/OME-367/extract-url4-sdk-from-the-legacy-tag-packagesurl4-python-sdk
status: todo
type: task
priority: P2
labels: [pkg/url4-python-sdk, Python SDK, agentic, deferred]
created: 2026-07-08
closed:
---

Stand up `packages/url4-python-sdk` (publishes as `url4` on PyPI) by extracting the url4
executor (grammar/AST/resolver) from `apps/server/.../url4_executor/` at tag
`legacy-monorepo-2026-07-08`. Gate: url4 grammar ownership confirmed post-reshuffle (OME-363).
