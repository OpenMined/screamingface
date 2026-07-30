---
ticket: OME-586
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-25
---

# OME-586 — Enable `frequency_penalty` and `presence_penalty` where the transform carries them

## Intent

The fail-closed chat-parameter classifier rejects `frequency_penalty` and `presence_penalty` for every
provider. OpenRouter and Hugging Face accept both and their INSTALLED litellm transforms carry them onto
the wire verbatim. Both are standard OpenAI-compatible repetition controls agentic callers expect, and
both are already surfaced as observed-but-disabled fields in the detailed `/v1/model-parameters` contract.
This unit promotes both to ENABLED rules on OpenRouter and Hugging Face ONLY, validated as bounded numbers.

## Reachability proof (§9, done at DESIGN)

Probe against the installed transforms (litellm 1.87.0), each field individually and together:

- **OpenRouter** (`OpenrouterConfig`): `frequency_penalty` → wire verbatim; `presence_penalty` → wire
  verbatim. → ENABLE both.
- **Hugging Face** (`HuggingFaceChatConfig`): `frequency_penalty` → wire verbatim; `presence_penalty` →
  wire verbatim. → ENABLE both.
- **Anthropic** (`AnthropicConfig`): `get_supported_openai_params` carries NEITHER; `map_openai_params`
  (drop_params) drops both → EXCLUDE.
- **Gemini** (`build_generate_content_body`): the builder `config_map` renders only max_tokens/temperature/
  top_p/top_k (+ stop/tools) — no penalty home. → EXCLUDE.

(The same probe confirmed `logprobs`/`top_logprobs` also reach the wire on both OpenAI-compatible
providers; those are a separate output-introspection feature and are deferred to their own unit.)

## Design (confirmed)

Mirrors OME-585 (`seed`) exactly — both penalties are ALREADY observed in the sampling constants, so
enabling = add the rule; NO new observation. Concretely:

- Core `standard_parameters.py`: add one shared `PENALTY_SCHEMA = ParameterSchema(type="number",
  minimum=-2, maximum=2)` (the OpenAI-compatible range both penalties share — DRY).
- OpenRouter / Hugging Face `parameters.py`: add `direct_rule("frequency_penalty", schema=PENALTY_SCHEMA,
  …)` and `direct_rule("presence_penalty", schema=PENALTY_SCHEMA, …)`.
- OpenRouter / Hugging Face `plugin.py`: NO change — both fields are already in
  `REVIEWED_ENDPOINT_OBSERVATIONS` / `HF_STATIC_PARAM_OBSERVATIONS`, so ruled + already-observed =
  ENABLED with existing evidence.
- Anthropic / Gemini: NO source change (excluded by the §9 proof); add exclusion guards pinning them
  unruled → fail closed `unknown`.

## Prior-test change (APPROVED-pattern check)

Enabling both flips their OpenRouter/HF overlay status disabled→enabled, which contradicts the
disabled-list assertions in `test_observed_but_unruled_field(s)_are_visible_but_disabled`
(openrouter + hf) and the disabled-loop in the openrouter "every observed sampling field" test.

Removing `frequency_penalty`/`presence_penalty` from those disabled tuples is a prior-test modification
(rule 5). This mirrors the approved `seed` move in OME-585 (`371c65cf`) and the `stop` move in OME-582
(`dc63ba00`) EXACTLY. **Approved by the owner** ("Approve (mirror seed/stop)") — enable
both on OpenRouter + HF as bounded [-2, 2] number rules, make the two mirrored disabled→enabled overlay
edits, retain the disabled guard for the still-unproven `top_p`, and keep Anthropic + Gemini excluded.
Everything else is additive.

## Planned changes

Source (3):
- `src/aigateway/core/standard_parameters.py` — `PENALTY_SCHEMA`.
- `src/aigateway/plugins/{openrouter,huggingface}_provider/parameters.py` — two `direct_rule`s each.

Tests (6): core schema; openrouter + hf overlay (enabled-with-evidence + the disabled-tuple edit) and
projection (reach dispatch/installed-transform + out-of-range fail-closed); anthropic + gemini exclusion
guards.

## Test plan (RED first)

- Core (`test_standard_parameters.py`): `PENALTY_SCHEMA` accepts -2/0/2 (inclusive bounds), rejects
  ±2.0001 (out of range) and a non-number.
- Overlay (openrouter + hf): both penalties ENABLED with evidence; disabled guards for the still-unruled
  fields RETAINED.
- Projection (§9): openrouter — both reach `litellm.acompletion` captured kwargs AND the installed
  `OpenrouterConfig` transform wire body; out-of-range fails closed 400. hf — reach the installed
  `HuggingFaceChatConfig` transform; out-of-range fails closed.
- Exclusion guards: anthropic + gemini rule sets do NOT contain either field (stay rejected `unknown`).

## Acceptance

- Both enabled on OpenRouter + Hugging Face, rejected (unruled) on Anthropic + Gemini; surfaced in the
  `/v1/models` summary and the detailed `/v1/model-parameters` contract.
- A caller value reaches the wire on the two enabled providers; an out-of-range value fails closed at
  classification before credential access.
- Existing behavior unchanged (except the penalty overlay moves); full gate suite green.

## Outcome

**Status: DONE.** `frequency_penalty` and `presence_penalty` are enabled as evidenced `direct` rules on
OpenRouter + Hugging Face only; rejected (unruled) on Anthropic + Gemini, each pinned by an exclusion
guard. All gates green.

### Actual changes (matched the plan)

Source (3):
- `src/aigateway/core/standard_parameters.py` — `PENALTY_SCHEMA = ParameterSchema(type="number",
  minimum=-2, maximum=2)` (one shared schema for both penalties — DRY).
- `src/aigateway/plugins/openrouter_provider/parameters.py` — imported `PENALTY_SCHEMA`; added
  `direct_rule("frequency_penalty", …)` + `direct_rule("presence_penalty", …)`.
- `src/aigateway/plugins/huggingface_provider/parameters.py` — same rule additions; also refreshed the
  module implementation note (penalties removed from the "left UNRULED" list, added to the "now ruled" list).
- No `plugin.py` change on either provider: both penalties are ALREADY in the sampling observation
  constants (`REVIEWED_ENDPOINT_OBSERVATIONS` / `HF_STATIC_PARAM_OBSERVATIONS`), so ruled +
  already-observed = ENABLED with existing evidence (the `seed` case).

Tests (6): core schema (inclusive bounds/out-of-range/non-number); openrouter + hf overlay
(enabled-with-evidence + the approved disabled→enabled tuple edit) and projection (reach dispatch +
installed-transform tripwire + out-of-range fail-closed); anthropic + gemini exclusion guards.

### Range validation (honest contract)

The `[-2, 2]` bound was cross-checked against the OpenAI-compatible provider contract before commit: the
installed `openai` SDK types document both penalties as "Number between -2.0 and 2.0", the installed
litellm transform applies no differing clamp (passthrough), and the OpenRouter + Hugging Face router
docs state the same `[-2.0, 2.0]` range. So the schema neither over- nor under-advertises the providers'
real accepted range.

### Gates

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only` → ALL GATES GREEN
(ruff check, ruff format --check, pyright, check_no_enterprise, pytest --cov ≥80). One in-loop fix: an
E501 long-line in a new HF projection test (inline comment) — moved the comment to its own line; purely
mechanical, additive.

`--skip-append-only` justification: the ONLY prior-test deletions vs HEAD are the two APPROVED
disabled→enabled tuple edits (removing `frequency_penalty` + `presence_penalty` from the OpenRouter and
Hugging Face overlay disabled loops) plus a reword of the OME-585 comment; everything else purely
additive. Confirmed by `git diff HEAD -- apps/aigateway/tests | grep '^-'`.

### Deviations

- **Migrations:** N/A — no schema or ORM model touched.
- Prior-test edit approved by the owner (mirrors OME-585 `371c65cf` / OME-582 `dc63ba00`).

Commit: `3d11bb47` — feat(aigateway): enable frequency_penalty and presence_penalty on
OpenAI-compatible providers (10 files, +247/-10; `Refs: OME-586, OME-479`).
