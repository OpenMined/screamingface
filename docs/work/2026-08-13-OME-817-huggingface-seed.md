---
ticket: OME-817
stack: aigateway
status: done
started: 2026-08-13
finished: 2026-08-13
---

# OME-817 — Expand HuggingFace model seed with live-verified router backends

## Intent

Expand the HuggingFace provider seed (`_default_model_slugs()`) with text-generation models the
HF unified router actually serves, each pinned to a live `:provider` backend, so the SF model
dropdown (`GET /v1/models`, SF-284) and url4 leaves can address the current open-weight lineup.
Part of epic OME-815. Landed with OME-818 in one aigateway PR (same worktree).

## Method — verify-then-seed

Candidate repos (HF-50 text tiers) intersected against live `GET https://router.huggingface.co/v1/models`
(131 models, 2026-08-13). Kept only repos served as chat with a live text-output backend; picked
the cheapest tool-supporting live provider. 29 doc repos dropped (not on router — embeddings, GGUF
quants, self-host-only weights). Deduped against the 5 existing seeds by repo path (dropped
`deepseek-ai/DeepSeek-R1`, `openai/gpt-oss-120b` — already seeded) → **19 new** (24 total).

## Planned changes

- `apps/aigateway/src/aigateway/plugins/huggingface_provider/settings.py` — append 19 verified
  `huggingface/<org>/<model>:<provider>` entries to `_default_model_slugs()`.
- `apps/aigateway/tests/unit/huggingface/test_huggingface_settings.py` — ADD: every new entry
  present, passes `_validate_model_slug`, and `pinned_router_target` returns a `(repo, backend)`.

No schema/model change → no migration (S1 n/a). No Tortoise → tortoise-dev n/a.

## Test plan

- RED: new presence/backend test fails against the current 5-seed list.
- GREEN: after the seed edit, all pass; HF unit suite green.
- Invariant: 3-segment `<org>/<model>:<provider>` router form (not the forbidden 4-segment
  path form); every seed carries an explicit backend (`pinned_router_target` non-None).

## Acceptance

- `_default_model_slugs()` returns 24 router-form entries; construction validator accepts all;
  `run_gates.py aigateway` green. HF ids are aigateway-only (not mirrored to url4.toml — colon).

## Outcome

- **Actual files:** as planned — `huggingface_provider/settings.py` (+19 seeds, 5→24),
  `test_huggingface_settings.py` (+`_OME_817_ADDED` + backed-additions test), ledger, mirror.
- **Commits:** 5f9a477b — feat(aigateway): expand HuggingFace model seed with 19 live-verified router backends
- **Gates:** `run_gates.py aigateway` ALL GREEN (shared B+C run). HF+anthropic suites 309 passed.
- **Deviations:** none for HF (pure addition — no prior test/fixture modified).
