---
id: OME-889
linear_url: https://linear.app/openmined/issue/OME-889/raise-the-local-stacks-openrouter-gateway-concurrency-to-match-the
status: in_progress
type: task
priority: high
labels: [py-screamingface, agentic, autonomous, task]
created: 2026-08-19
closed:
---

# Raise the local stack's OpenRouter gateway concurrency to match the Engine's 32-call fan-out

Short-term unblock for the admission-queue timeouts `OME-886` diagnoses. `just stack-up`
launches the AI Gateway at its code default of 4 concurrent calls per provider while one
Engine evaluation fans out up to 32; queued calls burn the Engine's 600s per-call budget
inside the gateway's semaphore and die without ever reaching OpenRouter.

Change: one env line in the gateway launch block of `packages/screamingface/justfile` —
`AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES='{"openrouter": 32}'`.

Out of scope: hosted deployments (operator action via the aigateway chart's `extraEnv`),
the gateway code default, and the 600s timeout itself. Long-term fix: `OME-886`.

Ledger: `docs/work/2026-08-19-OME-889-stack-openrouter-concurrency.md`
