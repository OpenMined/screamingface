---
id: OME-899
linear_url: https://linear.app/openmined/issue/OME-899/authenticate-protected-scoreboard-requests-in-the-python-sdk
status: In Progress
priority: P1
labels: [py-screamingface, auth+subsidies, autonomous, agentic]
created: 2026-08-19
closed:
---

# Authenticate protected Scoreboard requests in the Python SDK

The Python SDK authenticates hosted Engine requests but does not authenticate its Scoreboard HTTP
client, so protected `get_score(...)` and `submit(...)` operations receive a Cloudflare Access 302
instead of reaching the Scoreboard API.

Add origin-aware Scoreboard authentication for synchronous and asynchronous Clients, preserve
anonymous public reads, and permit authentication replay only for safe reads or the
idempotency-keyed score submission. Include Scoreboard authentication in logout and shutdown, and
keep the public submission interface free of private header manipulation.

Full scope and acceptance criteria: the Linear issue body.
