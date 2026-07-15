---
ticket: OME-443
stack: repo
status: in_progress
started: 2026-07-15
finished:
---

# OME-443 — url4 Cloud Runner (epic): spec, plan & ticket cascade

## Intent
Design → spec → plan the url4 Cloud Runner (a cloud service executing url4 ensemble DAGs as long-running >15 min distributed jobs: FastAPI REST+WS control plane in `apps/runner`, Docker/k8s `JobRunner` substrate, NATS JetStream event streaming, Postgres session/node state, session tokens, owned-internal vs external-uncontrolled node split). File the sub-issue cascade under this epic and reconcile the stale `.claude/task-board.local.md` label taxonomy against live Linear.

## Planned changes
- `docs/spec/2026-07-15-url4-cloud-runner-spec.md` — the technical spec (folds in the 6-lens validation findings).
- `docs/plan/2026-07-15-url4-cloud-runner.md` — phased implementation plan.
- `docs/tasks/2026-07-15-url4-cloud-runner.md` — Linear mirror for OME-443.
- `.claude/task-board.local.md` — reconcile the `landing` + `type`/`epic_group` label axes to match live Linear IDs.
- Linear: OME-443 epic (filed) + the SDLC-unit sub-issue cascade.

## Test plan
Planning unit — no product code. Validation = the 6-lens adversarial-review workflow (`wf_100c27c9-f4d`) + spec self-review + owner plan review before any implementation ticket starts.

## Acceptance
- Spec + plan written on branch `OME-443-url4-cloud-runner`.
- Sub-issue cascade filed under OME-443 with verified-live labels (incl. explicit docker-compose and Helm local-dev validation tickets).
- Card reconciled against live Linear.
- Owner reviews and approves the plan.

## Outcome (fill at the end — required before COMMIT)
- **Actual files:** <tbd>
- **Commits:** <tbd>
- **Gates:** <tbd — planning unit; N/A or doc lint>
- **Deviations:** <tbd>
