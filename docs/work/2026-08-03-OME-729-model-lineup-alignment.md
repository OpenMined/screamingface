---
ticket: OME-729
stack: aigateway
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-729 — Align the small-model lineup across aigateway seeds and url4.toml

## Intent

Close the recon-flagged gap: 4 openrouter models are dev-seeded + notebook-used but
absent from the plugin registry and url4.toml → catalog passes, execution fails.
Also gives OME-728's CorrectiveEnsemble real small-model members.

## Planned changes

- `apps/aigateway/.../openrouter_provider/settings.py` — 4 slugs added to
  `_default_model_slugs()`
- `apps/url4-cloud/url4.toml` — 4 matching `[[aigateway.models]]` routes (done)

## Test plan

- `test_declared_models_match_aigateway.py` green (the pinning test IS the spec)
- aigateway openrouter settings tests stay green

## Acceptance

- Both suites green; notebook-06 lineup models resolve at execution.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned + the two openrouter seed-pin test lists (the
  guards for exactly this deliberate change).
- **Commits:** `bbbdb625` feat: add four OpenRouter ensemble models to the gateway and engine lineups (pushed to upstream/OME-605-screamingface-client-v1).
- **Gates:** aigateway 2294 green; url4-cloud pinning test green.
- **Deviations:** none. Live gateway serves all 9 openrouter models.
