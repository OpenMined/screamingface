---
ticket: OME-584
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-24
---

# OME-584 — Enable structured output (`response_format`) where the transform carries it

## Intent

The fail-closed chat-parameter classifier rejects `response_format` for every provider. OpenRouter
and Hugging Face accept it and their INSTALLED litellm transforms carry it onto the wire verbatim
(both `{"type":"json_object"}` and `{"type":"json_schema", …}`); structured output is a core
capability agentic callers expect. This unit promotes `response_format` to an ENABLED rule on
OpenRouter and Hugging Face ONLY, validated as an object with a bounded `type` discriminator.

## Reachability proof (§9, done at DESIGN)

Probe against the installed transforms (litellm 1.87.0):

- **OpenRouter** (`OpenrouterConfig`): `response_format` reaches the wire VERBATIM for both
  `json_object` and `json_schema`. → ENABLE.
- **Hugging Face** (`HuggingFaceChatConfig`): same — verbatim on the wire for both forms. → ENABLE.
- **Anthropic** (`AnthropicConfig.map_openai_params`): `{"type":"json_object"}` → dropped
  (`keys=[]`, absent from wire); `{"type":"json_schema"}` → rewritten into a synthetic
  `json_tool_call` tool + forced `tool_choice`, `response_format` ABSENT from wire. → EXCLUDE
  (not carried as `response_format`; would also collide with the OME-583 tools channel).
- **Gemini** (`build_generate_content_body`): renders only max_tokens/temperature/top_p/top_k/
  stop/tools — no `response_format` home. → EXCLUDE.

## Design (confirmed)

`response_format` becomes a first-class, evidenced parameter (rule-only authorization, no separate
dispatch path — same discipline as stop/tools). Concretely:

- Core `standard_parameters.py`: add `RESPONSE_FORMAT_SCHEMA` — a `ParameterSchema(type="object",
  object_discriminator="type", object_discriminator_enum=("text","json_object","json_schema"))`.
  The enum is the FULL documented OpenAI range, so the gateway does not narrow the provider's valid
  set (avoids narrowing a provider's accepted range). Add a general
  `direct_parameter_observations(request_paths,
  *, source)` helper (reused for later non-sampling fields), mirroring `tool_parameter_observations`.
- OpenRouter / Hugging Face `parameters.py`: add `direct_rule("response_format", schema=
  RESPONSE_FORMAT_SCHEMA, …)` to the rule set. (Adding a new rule moves the contract digest via the
  new request_path — no revision bump needed, consistent with how stop/tools were added.)
- OpenRouter / Hugging Face `plugin.py`: concatenate `direct_parameter_observations(
  ("response_format",), source=<provider static label>)` into `chat_parameter_observations` — kept
  OUT of the sampling discovery constants (response_format is not a sampling field), exactly as
  tools were, so the strict discovery-parser tests keep their meaning.
- Anthropic / Gemini: NO change (excluded by the §9 proof).

## Planned changes

Source (5):
- `src/aigateway/core/standard_parameters.py` — `RESPONSE_FORMAT_SCHEMA` + `direct_parameter_observations`.
- `src/aigateway/plugins/{openrouter,huggingface}_provider/parameters.py` — `direct_rule("response_format", …)`.
- `src/aigateway/plugins/{openrouter,huggingface}_provider/plugin.py` — concatenate the response_format observation.

## Test plan (RED first)

- Core (`test_standard_parameters.py`): `RESPONSE_FORMAT_SCHEMA` accepts `{type:json_object}` /
  `{type:json_schema,…}` / `{type:text}`; rejects an unknown `type` (`{type:xml}`), a typeless
  object, and a non-object (string); `direct_parameter_observations` builds one observation per path
  with the given source.
- Overlay (openrouter + hf): `response_format` ENABLED with evidence (`provider.support=supported`,
  provider's static source); present in the summary.
- Projection/dispatch (§9 proofs): openrouter — `response_format` reaches `litellm.acompletion`
  captured kwargs AND the installed `OpenrouterConfig` transform wire body (json_object +
  json_schema); malformed `type` → 400 `{response_format: malformed}`, nothing captured. hf —
  reaches the installed `HuggingFaceChatConfig` transform wire body; malformed `type` fails closed.
- Exclusion guards: anthropic + gemini rule sets do NOT contain `response_format` (stays rejected
  `unknown`), so the exclusion is pinned by a test, not just by omission.

## Acceptance

- `response_format` enabled on OpenRouter + Hugging Face, rejected (unruled) on Anthropic + Gemini;
  surfaced in the `/v1/models` summary and the detailed `/v1/model-parameters` contract.
- A caller `response_format` reaches the wire on the two enabled providers; a non-object or unknown
  `type` fails closed at classification before credential access.
- Existing behavior unchanged; full `aigateway` gate suite green.

## Outcome

**DONE.** `response_format` is enabled on OpenRouter + Hugging Face and rejected (unruled) on
Anthropic + Gemini, matching the §9 installed-transform reachability proof exactly. It surfaces in
the `/v1/models` summary and the detailed `/v1/model-parameters` contract with honest evidence; a
caller `response_format` reaches the wire on the two enabled providers for BOTH the `json_object`
and `json_schema` forms, while a non-object or unknown `type` fails closed at classification before
any credential access. No existing parameter behavior changed.

### Actual changes vs planned

Matched the plan. Source (5 files):

- `core/standard_parameters.py` — `RESPONSE_FORMAT_SCHEMA` (`object` gated by a `type` discriminator
  over the full documented range `text|json_object|json_schema`, so the gateway does not narrow the
  provider's valid set) + `direct_parameter_observations(request_paths, *, source)` (evidence for
  non-sampling `direct` fields, mirroring `tool_parameter_observations`; provider-agnostic).
- `plugins/{openrouter,huggingface}_provider/parameters.py` — `direct_rule("response_format",
  schema=RESPONSE_FORMAT_SCHEMA, …)` added to each rule set.
- `plugins/{openrouter,huggingface}_provider/plugin.py` — `direct_parameter_observations(
  ("response_format",), source=<provider static label>)` concatenated into
  `chat_parameter_observations` (kept OUT of the sampling discovery constants, so the strict
  discovery-parser tests keep their meaning).
- Anthropic / Gemini: NO change (excluded by the §9 proof).

Tests (append-only; new functions only, no prior test modified — verified zero deletions vs HEAD):

- `test_standard_parameters.py` — `RESPONSE_FORMAT_SCHEMA` accept/reject (all three types; unknown
  type, typeless object, non-object all fail closed; structural json-schema render);
  `direct_parameter_observations` one-per-path + empty-in-empty-out.
- OpenRouter overlay + projection — enabled-with-evidence; both forms reach `litellm.acompletion`;
  malformed `type` → 400 `{response_format: malformed}` nothing dispatched; installed
  `OpenrouterConfig` transform tripwire (both forms verbatim on the wire).
- Hugging Face overlay + projection — enabled-with-evidence; ruled; both forms reach the installed
  `HuggingFaceChatConfig` transform verbatim; malformed `type` fails closed.
- Exclusion guards — Anthropic + Gemini rule sets do NOT contain `response_format` (stays rejected
  `unknown`), pinning the exclusion by a test rather than by omission.

### Gates

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only` → **ALL GATES GREEN** (ruff check,
ruff format --check, pyright, check_no_enterprise, pytest --cov 91.27% ≥ 80%).

### Deviations

1. **`--skip-append-only`.** The mechanical append-only check flags any test file that differs from
   HEAD; these edits append new functions to existing suites, so they trip it. Verified genuinely
   additive — `git diff HEAD -- tests/` shows every test file at `N 0` (zero deletions) — so the
   rule 5 (append-only) holds and the flag skips a false positive, not a real violation.
2. **One `ruff format` reflow** of a single new HF test block (collapsed a multi-line
   `_dispatch_body({...})` call that fit on one line); additive-only confirmed after the reformat.
3. **One flaky gate failure, diagnosed not fixed.** The first full gate run failed
   `test_api_key_validation_http.py::test_validation_session_shares_one_absolute_deadline` — an
   untouched subsystem with a 30 ms wall-clock total-deadline against a 20 ms handler sleep, load-
   sensitive under the 1612-test/102s run. It passed 3/3 in isolation and the re-run was fully green,
   confirming an environmental timing flake unrelated to this change. Not modified (append-only + do
   not weaken a gate).

## Commit

`e126947a` — feat(aigateway): enable structured output (response_format) as a chat parameter —
`Refs: OME-584, OME-479`. 12 files (5 source, 7 tests), +337/-8; every test file is additions-only
(0 deletions vs HEAD — append-only rule 5 satisfied), the 8 deletions are source-side (the two
`plugin.py` return-statement reflows).
