---
ticket: OME-818
stack: aigateway
status: done
started: 2026-08-13
finished: 2026-08-13
---

# OME-818 — Expand Anthropic direct model seed with live-verified Claude ids

## Intent

Add the current-generation direct Claude ids to the Anthropic provider seed (`_default_models()`),
the single source of the SF Settings model dropdown (SF-284), so ensembles can address Opus 5 /
Fable 5 / Sonnet 5 and the 4.x back-catalog on the direct Anthropic API path (Tavily web-search
loop). Part of epic OME-815; landed with OME-817 in one aigateway PR.

## Method — verify-then-seed

Verified against the live Anthropic `GET /v1/models` (2026-08-13): returns `claude-opus-5`,
`claude-sonnet-5`, `claude-fable-5`, `claude-opus-4-8/-4-7/-4-6`, and dated `claude-opus-4-5-*`,
`claude-haiku-4-5-*`, `claude-sonnet-4-5-*`. New vs the current 5 seeds → 5 additions:
`claude-opus-5`, `claude-fable-5`, `claude-sonnet-5`, `claude-opus-4-6`, `claude-opus-4-5`
(alias form, matching the existing seed's alias convention for the 4-5 tier).

## Planned changes

- `apps/aigateway/src/aigateway/plugins/anthropic_provider/settings.py` — extend `names` in
  `_default_models()` to 10, newest-first per tier (opus → fable → sonnet → haiku).
- `apps/aigateway/tests/unit/anthropic/test_settings.py` — update the inline exact model-name
  pin (5 → 10) and ADD a focused test: new ids present, unprefixed + hyphenated (no dots),
  `litellm_params == {"model": f"anthropic/{id}"}`.

No schema/model change → no migration (S1 n/a). No Tortoise → tortoise-dev n/a.

## Test plan

- RED: the inline exact pin fails (5 != 10); new-ids test fails (absent).
- GREEN: after the seed edit, all pass; anthropic unit suite green.
- Invariant: every id is unprefixed + hyphenated; litellm model string is `anthropic/<id>`.

## Acceptance

- `_default_models()` returns 10 verified direct ids; `run_gates.py aigateway` green.
- Mirrorable to url4.toml (no colon) — handled in OME-819.

## Outcome

- **Actual files:** `anthropic_provider/settings.py` (`names` 5→10 + docstring), `test_settings.py`
  (exact pin 5→10 + new-ids test); **plus** `anthropic_provider/thinking.py` —
  `MANUAL_THINKING_MODELS` += `claude-opus-4-5` (blast-radius: litellm's installed transform maps
  opus-4-5 to a manual budget, and `test_the_budget_table_matches_the_installed_transform` requires
  the set to match). Ledger + mirror.
- **Commits:** 2cf90ce1 — feat(aigateway): expand Anthropic direct model seed with 5 live-verified Claude ids
- **Gates:** `run_gates.py aigateway` ALL GREEN (shared B+C run).
- **Deviations:** (1) updated the inline exact model-name pin (5→10) — owner-approved prior-test
  change (call-and-return gate 2026-08-13, same pattern as OME-816), applied via
  `--skip-append-only`. (2) Registered `claude-opus-4-5` in `MANUAL_THINKING_MODELS` (production
  code, necessary for the new model — not a test change). `INTERLEAVED_BETA_MODELS` deliberately
  left unchanged (existing fail-closed note excludes Opus 4.5).
