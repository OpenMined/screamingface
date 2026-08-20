---
id: OME-908
linear_url: https://linear.app/openmined/issue/OME-908/fair-schedule-concurrent-engine-runs-so-one-large-benchmark-run-doesnt
status: Backlog
priority: P2
labels: [screamingface-engine, human, design-session]
created: 2026-08-20
closed:
---

# Fair-schedule concurrent Engine runs so one large benchmark run doesn't starve others

One full DRACO run is ~20k model calls (100 cases × ~40 criteria × 5 judge passes, nearly all
to provider `openrouter`). Empirically, while one user runs DRACO the next user is starved
until it completes — the shared downstream capacity is served first-come-first-served, not
interleaved. We want fair scheduling so N concurrent runs each make proportional progress.

Likely locus: the gateway's per-provider FIFO concurrency slot (`AIGW_PROVIDER_MAX_CONCURRENCY = 4`,
keyed by model prefix → one `openrouter` semaphore), which is run/tenant-blind. Fairness belongs
in the Engine, which owns run/tenant context (`apps/screamingface-engine`). First task is to
confirm the exact starvation mechanism before committing to a design.

Recommended direction (owner decides — design-session): a work-conserving fair scheduler at the
Engine dispatcher. Alternatives listed in the Linear issue: per-run fair-share of slots, aging /
anti-starvation, chunked interleaving, QoS lanes, per-user caps, raising the downstream ceiling,
cache prefill (`OME-907`), and a distributed fair queue for multi-worker scale-out.

Full scope, mechanism trace, and the ranked option list live in the Linear issue.

Related: `OME-907` (AIGateway cache prefill miss on first-time DRACO runs — reduces the load
that causes this).
