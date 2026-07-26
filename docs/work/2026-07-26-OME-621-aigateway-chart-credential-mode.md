---
ticket: OME-621
stack: aigateway
status: in_progress
started: 2026-07-26
finished:
---

# OME-621 — expose AIGATEWAY_CREDENTIAL_MODE in the aigateway helm chart

## Intent

`AIGATEWAY_CREDENTIAL_MODE` is fully implemented in the app (OME-588, commit `ddc54c67`) but
unreachable through the chart: `templates/configmap.yaml` renders no such key and there is no
`extraEnv` escape hatch, so every helm install is silently pinned to `byok`. Shared
(admin-provisioned) credential mode — one operator-supplied provider key serving all authenticated
users — cannot be deployed at all. Expose it the same way `cfAccess` already is, so a local kind
install can run shared mode with an admin-provisioned OpenRouter key behind Cloudflare Access.

## Planned changes

- `apps/aigateway/charts/aigateway/values.yaml` — add `config.credentialMode: byok` (default
  preserves today's behaviour), with a comment pointing at the two valid values.
- `apps/aigateway/charts/aigateway/templates/configmap.yaml` — render
  `AIGATEWAY_CREDENTIAL_MODE: {{ .Values.config.credentialMode | quote }}`.

## Test plan

Chart templating, not Python — the gate is `helm template` output, not pytest:

- `helm template` with no override renders `AIGATEWAY_CREDENTIAL_MODE: "byok"` (no behaviour change
  for existing installs).
- `helm template --set config.credentialMode=shared` renders `AIGATEWAY_CREDENTIAL_MODE: "shared"`.
- `helm lint` passes.
- Invalid values remain rejected at app startup by the existing validator (`config.py:209-215`) —
  deliberately NOT re-validated in the chart, to keep one source of truth.

## Acceptance

The ConfigMap carries `AIGATEWAY_CREDENTIAL_MODE`, defaulting to `byok` and settable to `shared`
via a plain chart value; `helm lint` clean; no app/python source touched.

## Outcome

- **Actual files:** `apps/aigateway/charts/aigateway/values.yaml` (added `config.credentialMode:
  byok` + comment) · `apps/aigateway/charts/aigateway/templates/configmap.yaml` (renders
  `AIGATEWAY_CREDENTIAL_MODE`). Matches planned exactly — no app/python source touched.
- **Commits:** see the OME-621 commit on `integration-branch`.
- **Gates:** `helm template` default → `AIGATEWAY_CREDENTIAL_MODE: "byok"`; `--set
  config.credentialMode=shared` → `"shared"`; `helm lint` 1 chart linted, 0 failed (icon INFO only).
  Verified the `cfAccess` block still renders alongside it. No Python touched, so `run_gates`
  categories (ruff/pyright/pytest) are N/A.
- **Deviations:** no TDD RED/GREEN — this is chart templating, not Python; the gate is
  `helm template` output. Chart-side validation of the enum was deliberately NOT added: the
  app's existing `config.py` validator stays the single source of truth.
