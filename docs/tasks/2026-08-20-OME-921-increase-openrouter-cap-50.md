---
id: OME-921
linear_url: https://linear.app/openmined/issue/OME-921/increase-openrouter-max-concurrency-cap-to-50
status: Backlog
priority: P2
labels: [aigateway, human, autonomous, task]
created: 2026-08-20
closed:
---

# Increase OpenRouter max-concurrency cap to 50

Raise the `openrouter` per-provider concurrency cap to 50 via
`AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES={"openrouter": 50}` (currently 32 on local; 4 default
elsewhere). Gives headroom above a single Engine run's ~32 fan-out so calls don't queue in the
gateway and burn the 600s Engine timeout. Override plumbing already exists
(`apps/aigateway/src/aigateway/config.py:120`, `core/concurrency.py`); this applies the value in
the cloud stack config. Finite (not `0`) keeps thundering-herd protection.

Related: `OME-919` (load-test the real ceiling), `OME-908` (fairness). Full detail in the Linear
issue.
