---
ticket: OME-593
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-24
---

# OME-593 — Wire Cloudflare Access config, startup validation, and Helm values

## Intent

Turn the feature on safely. Every way the gateway could come up *believing* it is protected
while actually admitting unauthenticated callers becomes a startup error.

## Outcome

- **Actual files:** `config.py` (5 settings + 2 validators + `cf_access_admin_email_set`),
  `main.py` (conditional resolver registration), `charts/aigateway/values.yaml`,
  `charts/aigateway/templates/configmap.yaml`, `apps/aigateway/docs/cloudflare-access.md`,
  `tests/unit/test_cf_access_settings.py` (13 tests).
- **Commits:** NONE — blocked, see OME-589 ledger deviation 1.
- **Gates:** `run_gates.py aigateway` ALL GREEN.
- **Fail-fast cases covered:** `cf_access_enabled` + `auth_enabled=false` (would make every
  caller anonymous behind a supposedly-federated gateway); missing team domain or AUD; a team
  domain carrying a scheme/port/path/userinfo (the JWKS URL is built by interpolating it, so
  a redirectable value is a total auth bypass — the gateway would verify attacker-signed
  assertions). Chart verified rendering disabled, enabled, and failing loudly on a missing
  required value.
- **Deviations:**
  1. `cf_access_admin_emails` is a raw comma-separated `str`, not `list[str]`:
     pydantic-settings JSON-decodes complex field types from the env var *before* any
     validator runs, so the operator-friendly format raised `SettingsError`. Parsing moved to
     the `cf_access_admin_email_set` property.
  2. Chart rendering had to be verified through `rtk proxy helm ...` — the rtk hook truncates
     `helm template` output, which silently looked like a broken template.
