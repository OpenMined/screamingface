---
ticket: OME-816
stack: aigateway
status: done
started: 2026-08-13
finished: 2026-08-13
---

# OME-816 — Expand OpenRouter model seed with live-verified slugs

## Intent

The OpenRouter provider seed (`_default_model_slugs()`) is the recommended bootstrap catalog for
url4 leaf models routed through OpenRouter. Expand it from 11 to the live-verified set drawn from
the Aug-2026 catalog docs (OpenRouter 50 + OpenAI 15 + Anthropic-on-OpenRouter), so ensembles and
benchmarks can address the current frontier + budget lineup. Part of epic OME-815.

## Method — verify-then-seed

Candidate slugs were intersected against the live `GET https://openrouter.ai/api/v1/models`
(409 models, fetched 2026-08-13). 65/65 candidates resolved (doc-corrupt rows corrected to live
ids: `mistralai/ministral-14b-2512`, `mistralai/mistral-medium-3-5`). Dropped as non-existent:
`deepseek/deepseek-v4-*-0423`, `openai/gpt-oss-120b:free`, retired `anthropic/claude-sonnet-3.7`.
Deduped against the 11 existing seeds → **58 new slugs** (69 total).

## Planned changes

- `apps/aigateway/src/aigateway/plugins/openrouter_provider/settings.py` — append 58 verified
  slugs to `_default_model_slugs()` return list (keep existing 11 + AIDEV-NOTE judge pins).
- `apps/aigateway/tests/unit/openrouter/test_openrouter_settings.py` — update the `_SEEDS`
  protocol-pin to the full 69, and ADD: presence-of-new-slugs, per-seed well-formedness
  (`_validate_gateway_slug`), and no-`:online`-variant assertions.
- Ledger + `docs/tasks/` mirror.

No schema/model change → no migration (S1 n/a). No Tortoise → tortoise-dev companion n/a.

## Test plan

- RED: new assertions fail against the current 11-seed list (new slugs absent) + the exact-pin
  fails (11 != 69).
- GREEN: after the seed edit, all pass; full openrouter unit suite stays green.
- Invariant protected: every seed is gateway-shaped `openrouter/<author>/<model>[:variant]`
  (construction validator) and none carries the dispatch-refused `:online` variant.

## Acceptance

- `_default_model_slugs()` returns 69 live-verified gateway ids; construction validators accept
  all; `run_gates.py aigateway` green.
- `:variant` slugs (`:batch`, `:free`) present but flagged aigateway-only (non-mirrorable to
  url4.toml — handled in OME-819).

## Outcome

- **Actual files:** as planned — `openrouter_provider/settings.py` (+58 seeds), `test_openrouter_settings.py` (`_SEEDS` pin 11→69 + 2 new invariant tests), ledger, `docs/tasks/` mirror.
- **Verification:** 65/65 candidates resolved vs live `openrouter.ai/api/v1/models` (2026-08-13); 58 net-new after dedup; seed 11→69.
- **Commits:** 680959f5 — feat(aigateway): expand OpenRouter model seed with 58 live-verified slugs
- **Gates:** `run_gates.py aigateway` ALL GREEN (ruff check, ruff format --check, pyright, check_no_enterprise, pytest --cov≥80). OpenRouter unit suite 843 passed.
- **Deviations:** `--skip-append-only` used to update the `_SEEDS` protocol-pin (11→69). Owner-approved 2026-08-13 (call-and-return confidence gate); the pin's own docstring designates it the single fixture updated on deliberate seed changes. Exact-equality assertion preserved; no prior test body altered; two invariant tests added (gateway-shape, no `:online`).
