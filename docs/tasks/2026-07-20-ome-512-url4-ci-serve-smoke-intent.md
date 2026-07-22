---
id: OME-512
linear_url: https://linear.app/openmined/issue/OME-512/url4-ci-fix-serve-smoke-expression-illegal-under-ome-508-missing-outer
status: Done
type: Bug
priority: P1
labels: [url4-python-sdk, url4-engine, autonomous, agentic]
created: 2026-07-20
closed: 2026-07-20
---

# url4 CI: fix serve-smoke expression illegal under OME-508

The `serve smoke` CI job's first eval `(/upper(hello world)!'go')` is an intent-less
group — OME-508 rejects it with 500 `missing_intent`. Add the outer `!''` (as every
sibling assertion already has). Red since OME-508; independent of the main merge.

See `docs/work/2026-07-20-OME-512-url4-ci-serve-smoke-intent.md`.
