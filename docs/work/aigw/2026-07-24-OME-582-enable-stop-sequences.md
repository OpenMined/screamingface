---
ticket: OME-582
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-24
---

# OME-582 — Enable `stop` sequences as a chat parameter across providers

## Intent

The fail-closed chat-parameter classifier rejects `stop` for every provider, even though
all four wired providers accept it and their INSTALLED transforms carry it onto the wire:

- Anthropic → `stop_sequences` (via `litellm` `get_optional_params` / `AnthropicConfig`)
- Gemini → `stopSequences` (via the gateway's own `build_generate_content_body`)
- OpenRouter → `stop` (OpenAI-compatible, via `litellm.get_optional_params`)
- Hugging Face → `stop` (OpenAI-compatible, via `litellm.get_optional_params`)

`stop` is already an OBSERVED-but-disabled field in each provider's detailed
`/v1/model-parameters` contract. This unit promotes it to an ENABLED rule so callers can
actually send stop sequences, backed by the union schema the core gained in OME-581
(`string | array[string]`).

## Reachability proof (§9, done at DESIGN)

`litellm.get_optional_params` (installed 1.87.0) returns `stop`/`stop_sequences` for
anthropic/openrouter/huggingface; the Gemini builder maps `stop` → `stopSequences` for both
`str` and `list[str]`. So `stop` reaches ALL four — every provider's guard flips to enabled.

## Planned changes

- `src/aigateway/core/standard_parameters.py` — add shared
  `STOP_SCHEMA = ParameterSchema(type=("string", "array"), item_type="string")`
  (no provider names — shared-vocabulary invariant holds).
- `src/aigateway/plugins/{anthropic,gemini,openrouter,huggingface}_provider/parameters.py` —
  add `direct_rule("stop", auth_modes=<provider>, schema=STOP_SCHEMA, projection_revision=…)`;
  update the implementation notes that declared `stop` unruled.
- Docstring/comment touch-ups where `stop` was cited as the example of "observed-but-unruled"
  (anthropic `discovery.py`, `plugin.py`).

## Test plan (RED first)

Rewrite the base-snapshot guards that lock `stop` unruled (sanctioned prior-test change —
each `stop` provably reaches its transform), and add positive proofs:

- gemini: rewrite `test_unruled_stop_is_rejected_fail_closed` (projection → accepted +
  `stopSequences`), `test_unruled_stop_is_visible_but_disabled_under_both_modes` (overlay →
  enabled), the `"stop" not in summary` line (→ in summary),
  `test_unruled_stop_is_rejected_so_it_can_never_reach_the_wire` (dispatch → reaches
  `generationConfig.stopSequences` on both auth paths).
- anthropic: rewrite `test_observed_but_unruled_stop_is_visible_but_disabled` (→ enabled),
  the `"stop" not in summary` line; add a transform proof (`stop` → `stop_sequences`).
- openrouter / huggingface: pull `stop` out of the observed-but-disabled loop, assert it
  enabled; add a `get_optional_params` proof (`stop` forwarded).
- Discovery-parser tests (assert `stop` is OBSERVED) and `finish_reason == "stop"` tests are
  unaffected and stay green.

## Acceptance

- `stop` enabled under every auth mode each provider offers; present as enabled in the
  `/v1/models` summary and the detailed contract.
- A caller `stop` (string or array of strings) reaches the wire; a malformed value fails
  closed at classification before credential access.
- Existing behavior unchanged; full `aigateway` gate suite green.

## Outcome

**Done.** `stop` is now an enabled chat parameter on all four wired providers, backed by a
transform-reachability proof for each.

**Commit:** `dc63ba00` — `feat(aigateway): enable stop sequences as a chat parameter`.

### Files changed (actual)

Source (6):
- `src/aigateway/core/standard_parameters.py` — added shared
  `STOP_SCHEMA = ParameterSchema(type=("string", "array"), item_type="string")` (union
  `string | array[string]`; no provider names — shared-vocabulary invariant holds).
- `src/aigateway/plugins/anthropic_provider/parameters.py` — `direct_rule("stop", …)` under
  both auth modes (`stop` → `stop_sequences` via the installed `AnthropicConfig`); implementation note
  refreshed.
- `src/aigateway/plugins/gemini_provider/parameters.py` — `direct_rule("stop", …)` under both
  auth modes (builder → `stopSequences`); implementation note refreshed (union schema unblocked it).
- `src/aigateway/plugins/openrouter_provider/parameters.py` — `direct_rule("stop", …)`
  (api-key; OpenAI-native `stop`).
- `src/aigateway/plugins/huggingface_provider/parameters.py` — `direct_rule("stop", …)`
  (api-key; OpenAI-native `stop`); implementation-note list trimmed.
- `src/aigateway/plugins/anthropic_provider/plugin.py` — observation comment corrected
  (`stop` now ruled → enabled, not observed-but-disabled).

Tests (9): the four base-snapshot `*unruled_stop*` guards rewritten into enabled/reachability
proofs, plus the two overlay in-place edits (stop dropped from the disabled loop → asserted
enabled) and the two summary polarity flips (`"stop" in summary`). New: a `malformed_stop`
fail-closed proof (gemini) and per-provider installed-transform reachability proofs
(anthropic `stop_sequences`; gemini `generationConfig.stopSequences` on both auth paths;
openrouter/huggingface `get_optional_params` → `stop`).

### Gates

`uv run .claude/scripts/run_gates.py aigateway` — ruff ✓, ruff format ✓, pyright ✓,
check_no_enterprise ✓, pytest --cov (≥80% enforced) ✓. All green.

### Deviations

- **Append-only check:** the 9 test edits modify prior (base-snapshot) tests, which the gate
  flags by design. These are the base-snapshot regression guards that locked `stop` unruled;
  rewriting them into enabled-proofs was explicitly approved (the "enable all four fields"
  Confidence-Gate decision), so the gate was run once with `--skip-append-only`. Every other
  gate ran unweakened. The removed tests are all `*unruled_stop*`/`*rejected*` guards; no
  unrelated test was changed (verified by diffing removed vs added `def test_` names).
- The planned `discovery.py` docstring touch-up was unnecessary — `stop` legitimately stays
  *observed* in discovery evidence and is now *also* ruled; no stale claim there.
- Scope was per-provider narrow: only `stop`. `tool_choice`/`response_format` (Gemini) and
  `response_format` (Anthropic) stay guarded — they do not reach their installed transforms
  (§9), so enabling them would be dishonest. Those belong to later units.
