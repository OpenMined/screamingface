---
id: OME-919
linear_url: https://linear.app/openmined/issue/OME-919/load-test-openrouter-concurrency-ceiling-and-validate-the-per-provider
status: Backlog
priority: P2
labels: [aigateway, human, autonomous, task]
created: 2026-08-20
closed:
---

# Load-test OpenRouter concurrency ceiling and validate the per-provider cap

Measure OpenRouter's real usable concurrency through AIGateway — goodput, 429 rate, latency,
cost — as the `openrouter` per-provider cap (`AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES`) is
ramped `4 → 16 → 32 → 64 → 0`, so the cloud value is chosen with data. `0` disables the
`provider_slot` semaphore entirely (`core/concurrency.py`), removing thundering-herd protection
and exposing OpenRouter's own account limits — use it only as a bounded, monitored "find the
ceiling" step on a test key, never as standing cloud config.

Deliverable: a recommended finite cloud `openrouter` value + the measured ceiling, recorded on
`OME-908` (it bounds any fair-scheduling design). Full method, safety notes, and metrics to
capture live in the Linear issue.

Related: `OME-908` (engine-side fair scheduling), `OME-907` (cache prefill miss changes the
load profile on warm re-runs).
