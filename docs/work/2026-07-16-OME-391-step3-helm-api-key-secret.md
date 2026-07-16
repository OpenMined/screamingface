---
ticket: OME-391
stack: scoreboard
status: done
started: 2026-07-16
finished: 2026-07-16
---

# OME-391 (step 3) — wire SCOREBOARD_SUBMISSION_API_KEY through the Helm chart

## Intent

Step 2 (PR #392) added `Settings.submission_api_key`, read from `SCOREBOARD_SUBMISSION_API_KEY`,
gating `POST /v1/scores` behind a placeholder shared key. Dmitry has already generated a real
key and shared it, expecting it usable in production — but the Helm chart has no mechanism to
set that env var at all. Confirmed via a full read of every file in
`apps/scoreboard/charts/scoreboard/`: the only secret-injection pattern that exists is
`database.existingSecret`/`existingSecretKey` for the DB URL; there's no generic
`extraEnv`/`extraEnvFrom` passthrough. Without this, the only ways to set the key are either
non-declarative (`kubectl set env`, silently wiped by the next `helm upgrade`) or insecure
(raw value committed to `values-prod.yaml`).

## Planned changes

- `apps/scoreboard/charts/scoreboard/values.yaml`: add
  `submissionApiKey: { existingSecret: "", existingSecretKey: "" }` (empty by default — unlike
  `database.existingSecret`, this one is optional; unset means the gate stays a no-op, matching
  today's actual production behavior).
- `apps/scoreboard/charts/scoreboard/templates/deployment.yaml`: add an optional `env` entry for
  `SCOREBOARD_SUBMISSION_API_KEY` via `secretKeyRef`, rendered only when
  `.Values.submissionApiKey.existingSecret` is set (`{{- if .Values.submissionApiKey.existingSecret }}`)
  — no `required`, since this field is optional by design.
- `apps/scoreboard/DEPLOYMENT.md`: document the new values fields next to the existing
  `SCOREBOARD_SUBMISSION_API_KEY` note.

## Test plan

This is a Helm chart, not an app-code change — no pytest coverage applies. Verification instead:
- `helm lint charts/scoreboard` clean, both with and without `submissionApiKey.existingSecret` set.
- `helm template` with the field unset → confirm no `SCOREBOARD_SUBMISSION_API_KEY` env entry
  renders (proves the optional-rendering guard works, and default behavior is unchanged).
- `helm template` with the field set (e.g. `--set submissionApiKey.existingSecret=test-secret
  --set submissionApiKey.existingSecretKey=api-key`) → confirm the rendered Deployment's `env:`
  includes a `secretKeyRef` entry for `SCOREBOARD_SUBMISSION_API_KEY` pointing at the given
  secret/key names.

## Acceptance

- Setting `submissionApiKey.existingSecret`/`existingSecretKey` in values makes
  `SCOREBOARD_SUBMISSION_API_KEY` available to the pod via a Kubernetes Secret reference —
  survives `helm upgrade`, never touches git.
- Leaving it unset renders identically to today (no new env entry, no behavior change).
- `helm lint` clean in both configurations.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `apps/scoreboard/charts/scoreboard/values.yaml` — added `submissionApiKey.existingSecret`/`existingSecretKey`, both empty by default.
  - `apps/scoreboard/charts/scoreboard/templates/deployment.yaml` — added the conditional `SCOREBOARD_SUBMISSION_API_KEY` env entry, guarded by `{{- if .Values.submissionApiKey.existingSecret }}`.
  - `apps/scoreboard/DEPLOYMENT.md` — replaced the existing "coordinate key distribution" note with concrete `kubectl create secret` + `helm upgrade --set` steps.
- **Commits:** this unit's commit (`Refs: OME-391`).
- **Gates:** `helm lint charts/scoreboard` clean in 3 configurations (default, `--set submissionApiKey.*`, `--values values-prod.yaml`). `helm template` confirmed: unset → no env entry rendered (unchanged default behavior); set → correct `secretKeyRef` rendered with the given secret/key names.
- **Deviations:**
  - Dmitry (review, PR #403) split this into its own sub-issue **OME-467** (parented under
    OME-391) and requested two changes before merge/deploy, from live evidence: the
    production Secret is already named `scoreboard-submission-api-key` (key
    `SCOREBOARD_SUBMISSION_API_KEY`), set via an out-of-band `kubectl set env` that Helm
    revision 12's values don't own.
    1. "Keep the rendered `secretKeyRef` required, not `optional: true`" — already true
       without any change: Kubernetes defaults `secretKeyRef` to required when `optional`
       is omitted, verified by re-reading the diff (no `optional:` key present anywhere).
    2. "Ensure the production Secret reference is supplied declaratively on every
       deploy" — added `submissionApiKey.existingSecret: scoreboard-submission-api-key` /
       `existingSecretKey: SCOREBOARD_SUBMISSION_API_KEY` directly to `values-prod.yaml`
       (matching the live Secret exactly), so every production `helm upgrade` renders it
       automatically — no `--set` flag needed. Verified via `helm template --values
       values-prod.yaml`.
  - Going forward, reference **OME-467** (not just OME-391) in commits/PR for this scope,
    per Dmitry's request.
