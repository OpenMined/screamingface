---
id: OME-443
linear_url: https://linear.app/openmined/issue/OME-443/url4-cloud-runner-distributed-long-running-execution-service-epic
status: in_progress
type: epic
priority: P1
labels: [url4-engine, pkg/url4-python-sdk, autonomous, agentic]
created: 2026-07-15
closed:
---

# OME-443 — url4 Cloud Runner (epic)

Cloud service that executes url4 ensemble DAGs as long-running (>15 min) distributed jobs: a REST + WebSocket control plane (FastAPI, `apps/runner`, port 9107), a Docker/k8s `JobRunner` substrate, NATS JetStream event streaming, Postgres session/node state, session tokens, and an owned-internal vs external-uncontrolled node distinction.

**Cross-cutting (D9):** lands in the new `apps/runner` service (labeled `url4-engine`) and in observability/streaming seams in `packages/url4` (`pkg/url4-python-sdk`). One sub-issue per SDLC unit.

**Locked decisions:** JobRunner port + Docker/k8s-Job adapters (not Temporal/Argo) · hybrid NATS auth (FastAPI mints subject-scoped creds; workers pub/sub JetStream directly) · control-plane-only child spawn · v1 = single-node happy path.

Spec `docs/spec/2026-07-15-url4-cloud-runner-spec.md` · Plan `docs/plan/2026-07-15-url4-cloud-runner.md` · Ledger `docs/work/2026-07-15-OME-443-url4-cloud-runner.md`. Sub-issues tracked in Linear under this epic.
