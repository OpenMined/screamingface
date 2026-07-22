---
id: OME-546
linear_url: https://linear.app/openmined/issue/OME-546
status: Backlog
type: Refactor
priority: P3
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: unify the duplicated ASGI error/lifespan helpers

peer/server.py and cli/_serve.py duplicate _send_error and _lifespan; no test cross-checks them, so the two entrypoints can drift into different error bodies. The server copy lacks the aclose() cleanup, so the entrypoint decides whether the owned HttpIOLayer is released — a behavioural fix, not a cleanup.

Spec → plan → owner approval before code. Under OME-537.
