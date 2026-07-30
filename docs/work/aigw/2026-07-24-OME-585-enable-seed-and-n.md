---
ticket: OME-585
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-24
---

# OME-585 — Enable `seed` and `n` where the transform carries them

## Intent

The fail-closed chat-parameter classifier rejects `seed` and `n` for every provider. OpenRouter and
Hugging Face accept both and their INSTALLED litellm transforms carry them onto the wire verbatim.
`seed` (deterministic sampling) and `n` (number of choices) are standard OpenAI-compatible controls
agentic callers expect. This unit promotes `seed` and `n` to ENABLED rules on OpenRouter and Hugging
Face ONLY, validated as bounded integers.

## Reachability proof (§9, done at DESIGN)

Probe against the installed transforms (litellm 1.87.0), both fields individually and together:

- **OpenRouter** (`OpenrouterConfig`): `seed` → wire verbatim; `n` → wire verbatim. → ENABLE both.
- **Hugging Face** (`HuggingFaceChatConfig`): `seed` → wire verbatim; `n` → wire verbatim. → ENABLE both.
- **Anthropic** (`AnthropicConfig`): `get_supported_openai_params` carries NEITHER `seed` nor `n`
  (litellm would drop them) → EXCLUDE.
- **Gemini** (`build_generate_content_body`): renders only max_tokens/temperature/top_p/top_k/stop/
  tools — no `seed`/`n` home. → EXCLUDE.

## Design (confirmed)

`seed` and `n` become first-class, evidenced parameters (rule-only authorization, no separate
dispatch path — same discipline as stop/tools/response_format). Concretely:

- Core `standard_parameters.py`: add `SEED_SCHEMA = ParameterSchema(type="integer")` (OpenAI seed is
  an arbitrary integer — no artificial bound) and `N_SCHEMA = ParameterSchema(type="integer",
  minimum=1)` (at least one choice).
- OpenRouter / Hugging Face `parameters.py`: add `direct_rule("seed", schema=SEED_SCHEMA, …)` and
  `direct_rule("n", schema=N_SCHEMA, …)` to the rule set.
- OpenRouter / Hugging Face `plugin.py`: `seed` is ALREADY observed in the sampling constants
  (`REVIEWED_ENDPOINT_OBSERVATIONS` / `HF_STATIC_PARAM_OBSERVATIONS`) → ruled + already-observed =
  ENABLED with existing evidence (NO new observation for seed). `n` is NOT observed → add
  `direct_parameter_observations(("n",), source=<provider static label>)`.
- Anthropic / Gemini: NO change (excluded by the §9 proof); their disabled/rejected guards stay.

## Approved prior-test change

Enabling `seed` flips its overlay status from disabled→enabled, which contradicts two prior-cycle
overlay assertions. With explicit approval (mirroring the committed OME-582 `stop` change exactly):

- `test_openrouter_parameter_overlay.py` — remove `seed` from the disabled-list tuple; add a
  `seed`-is-enabled-with-evidence assertion.
- `test_huggingface_parameter_overlay.py` — same.

The disabled guards for every field WITHOUT final-transform proof (top_p, frequency_penalty,
presence_penalty) are RETAINED unchanged. This is the sole prior-test edit; everything else is
additive.

## Planned changes

Source (5):
- `src/aigateway/core/standard_parameters.py` — `SEED_SCHEMA`, `N_SCHEMA`.
- `src/aigateway/plugins/{openrouter,huggingface}_provider/parameters.py` — `direct_rule("seed", …)`
  + `direct_rule("n", …)`.
- `src/aigateway/plugins/{openrouter,huggingface}_provider/plugin.py` — `direct_parameter_observations
  (("n",), …)` concatenated (seed already evidenced by the sampling constants).

## Test plan (RED first)

- Core (`test_standard_parameters.py`): `SEED_SCHEMA` accepts any int, rejects a float/non-int;
  `N_SCHEMA` accepts ≥1, rejects 0 (below minimum) and a non-int.
- Overlay (openrouter + hf): `seed` ENABLED with evidence (approved prior-test move); `n` ENABLED
  with evidence; disabled guards for the still-unruled fields RETAINED.
- Projection/dispatch (§9 proofs): openrouter — `seed`/`n` reach `litellm.acompletion` captured
  kwargs AND the installed `OpenrouterConfig` transform wire body; malformed `n` (0) / wrong-typed
  `seed` → 400, nothing captured. hf — reach the installed `HuggingFaceChatConfig` transform;
  malformed fails closed.
- Exclusion guards: anthropic + gemini rule sets do NOT contain `seed`/`n` (stay rejected `unknown`).

## Acceptance

- `seed` + `n` enabled on OpenRouter + Hugging Face, rejected (unruled) on Anthropic + Gemini;
  surfaced in the `/v1/models` summary and the detailed `/v1/model-parameters` contract.
- A caller `seed`/`n` reaches the wire on the two enabled providers; a wrong-typed or out-of-range
  value fails closed at classification before credential access.
- Existing behavior unchanged (except the approved seed overlay move); full gate suite green.

## Outcome

**Status: DONE.** `seed` and `n` are enabled as evidenced `direct` rules on OpenRouter + Hugging Face
only; rejected (unruled) on Anthropic + Gemini, each pinned by an exclusion guard. All gates green.

### Actual changes (matched the plan)

Source (5):
- `src/aigateway/core/standard_parameters.py` — `SEED_SCHEMA = ParameterSchema(type="integer")`
  (unbounded — OpenAI seed is arbitrary), `N_SCHEMA = ParameterSchema(type="integer", minimum=1)`.
- `src/aigateway/plugins/openrouter_provider/parameters.py` — imported the two schemas; added
  `direct_rule("seed", …)` + `direct_rule("n", …)`.
- `src/aigateway/plugins/openrouter_provider/plugin.py` — added `"n"` to the plugin-level
  `direct_parameter_observations((…), source=LOCAL_SOURCE)` (seed already in the sampling constant).
- `src/aigateway/plugins/huggingface_provider/parameters.py` — same rule additions; also refreshed the
  module implementation note (seed removed from the "left UNRULED" list; seed/n noted as now ruled).
- `src/aigateway/plugins/huggingface_provider/plugin.py` — added `"n"` to
  `direct_parameter_observations((…), source=STATIC_SOURCE)`.

Tests (6): core schema tests; openrouter + hf overlay (enabled-with-evidence + the approved seed
disabled→enabled move) and projection (reach dispatch + installed-transform tripwire + malformed
fail-closed); anthropic + gemini exclusion guards (seed/n stay unruled → fail closed `unknown`).

### Gates

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only` → ALL GATES GREEN
(ruff check, ruff format --check, pyright, check_no_enterprise, pytest --cov ≥80).

`--skip-append-only` justification: the ONLY prior-test deletions vs HEAD are the two approved
`seed` disabled→enabled tuple edits (openrouter + hf overlay), mirroring committed OME-582
(`dc63ba00`) for `stop`. Verified by `git diff HEAD -- apps/aigateway/tests | grep '^-'` = exactly
those two lines; everything else purely additive.

### Deviations

- **Flaky timing test.** In an ad-hoc full-suite run, `tests/unit/auth/test_login.py::
  test_unknown_user_timing_close_to_wrong_password` failed once (~15% vs the 10% timing-attack
  margin) under concurrent load. It is an untouched subsystem unrelated to parameter rules; it
  passed in isolation AND inside the formal gate run. NOT modified (append-only + don't-weaken-gate).
- **Migrations:** N/A — no schema or ORM model touched.
- **Migration deployment hook:** N/A — no schema change.

Commit: `371c65cf` — feat(aigateway): enable seed and n on OpenAI-compatible providers
(12 files changed, 272 insertions(+), 9 deletions(-)).
