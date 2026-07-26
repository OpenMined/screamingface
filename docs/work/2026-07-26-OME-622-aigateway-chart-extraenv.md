---
ticket: OME-622
stack: aigateway
status: in_progress
started: 2026-07-26
finished:
---

# OME-622 — generic extraEnv/extraEnvFrom passthrough in the aigateway chart

## Intent

The chart can only set environment it hardcodes: `envFrom` (one ConfigMap) plus four fixed `env`
entries, with no passthrough. Any app setting the chart does not explicitly template is
undeployable. Same root cause as [[OME-621]], and it recurs immediately — the OpenRouter plugin is
gated behind `AIGW_OPENROUTER_ENABLED` (default **false**, fail-closed), so
`POST /v1/admin/credential-pools` answers `400 api_key_not_supported` and no OpenRouter key can be
provisioned on a helm-deployed gateway. Per-plugin bespoke values do not scale: every provider owns
an `AIGW_<PROVIDER>_*` namespace. Add one generic escape hatch instead.

## Planned changes

- `apps/aigateway/charts/aigateway/values.yaml` — add `extraEnv: []` and `extraEnvFrom: []`.
- `apps/aigateway/charts/aigateway/templates/deployment.yaml` — emit both BEFORE the fixed
  entries. (Plan said "after"; corrected during implementation — Kubernetes applies duplicate
  env names LAST-wins, so extras must come first for the chart's secret-backed values to win.)

## Test plan

Chart templating — the gate is `helm template` output:

- Empty defaults render byte-identical to today (no `extraEnv` → no change).
- `--set-json 'extraEnv=[{"name":"AIGW_OPENROUTER_ENABLED","value":"true"}]'` renders that var.
- Ordering: a hostile `extraEnv` entry named `AIGATEWAY_JWT_SECRET` must be emitted BEFORE the
  real secret-backed one, so last-wins leaves the chart's value in effect.
- `helm lint` clean.
- Functional: with the flag set, an OpenRouter key provisions successfully into a shared pool.

## Acceptance

`extraEnv`/`extraEnvFrom` render on the container, defaults are a no-op, fixed env cannot be
shadowed, and the shared OpenRouter pool can be provisioned end-to-end.

## Outcome

- **Actual files:** `apps/aigateway/charts/aigateway/values.yaml` (`extraEnv: []`,
  `extraEnvFrom: []` + guidance comment) · `apps/aigateway/charts/aigateway/templates/
  deployment.yaml` (both rendered, extras first). No app/python source touched.
- **Commits:** see the OME-622 commit on `integration-branch`.
- **Gates:** `helm template` with defaults renders zero extra env (no-op). With
  `--set-json extraEnv=[...]` the var renders. **Shadow test:** a hostile
  `AIGATEWAY_JWT_SECRET` extra is emitted first and the real `secretKeyRef` entry last, so
  k8s last-wins keeps the chart's value. `helm lint` 1 linted / 0 failed. Verified live on
  kind: pod env order is `AIGW_OPENROUTER_ENABLED, AIGATEWAY_DATABASE_URL,
  AIGATEWAY_JWT_SECRET, AIGATEWAY_ADMIN_PASSWORD, AIGATEWAY_PROVISIONING_TOKEN`.
- **Functional acceptance:** with `AIGW_OPENROUTER_ENABLED=true` supplied via `extraEnv`,
  `POST /v1/admin/credential-pools` returned **201** (previously 400 `api_key_not_supported`),
  and a `/v1/chat/completions` call through the shared pool returned a real completion with
  `is_byok: false` — confirming the admin-provisioned credential backed the call.
- **Deviations:** ordering flipped from the plan (see Planned changes) — the plan's "after"
  would have let an operator shadow the DB/JWT secrets. No TDD RED/GREEN: chart templating,
  not Python; gate is `helm template` output.
