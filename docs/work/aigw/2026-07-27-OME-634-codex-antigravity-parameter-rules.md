---
ticket: OME-634
stack: aigateway
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-634 — Restore caller parameter support for Codex and Antigravity

## Intent

`routes/chat.py` classifies every request fail-closed: a caller parameter is dispatched only if a
provider rule authorizes it. `codex` and `antigravity` ship **zero** rules, so every optional field
a normal OpenAI-compatible client sends is rejected with `400 unsupported_parameters` before
dispatch. It also makes Codex's own caller `reasoning_effort` handling
(`plugins/codex_provider/plugin.py:96-101`) structurally unreachable — classification rejects the
field before `prepare_chat_body` ever runs.

This unit gives each provider its OWN rule set, derived from what that provider's installed final
transform provably puts on the wire. **No shared fallback rule set**: a provider that cannot carry a
field keeps rejecting it, and the detailed contract says so.

## Evidence — each provider's installed final transform

**Antigravity** — `plugins/antigravity_provider/message_adapter.py:33`
(`build_generate_content_body`), reached from `chat_handler.py:547`. It is byte-identical in the
relevant region to Gemini's own builder, which is why Gemini's proven rule set transfers exactly:

| Caller field | Wire | Mechanism |
|---|---|---|
| `temperature` | `generationConfig.temperature` | `config_map` |
| `top_p` | `generationConfig.topP` | `config_map` |
| `max_tokens` | `generationConfig.maxOutputTokens` | `config_map` |
| `provider_params.top_k` | `generationConfig.topK` | `config_map`, via the native wrapper |
| `stop` (string \| array[string]) | `generationConfig.stopSequences` | scalar coerced to a 1-element list |
| `tools` | `tools[0].functionDeclarations` | `_tool_to_gemini` unwraps the OpenAI `{"type":"function","function":{…}}` shape |

Nothing else is read from `optional_params`. There is no `toolConfig` home, so **`tool_choice` is
not enabled** — the same call Gemini already made. Antigravity is OAuth-only
(`supports_api_key() → False`), so every rule applies to that single mode.

**Codex** — `plugins/codex_provider/chat_handler.py:41` (`_build_payload`). It builds a **Responses**
payload and copies only `tools`, `tool_choice`, `reasoning`, `previous_response_id`, `truncation`
out of `optional_params` (plus a merged `include`). Everything else — `temperature`, `top_p`,
`max_tokens` — is **dropped before the request leaves the gateway**.

- **`reasoning_effort` → enabled.** `prepare_chat_body` converts it to `reasoning: {"effort": …}`
  and `_build_payload` carries `reasoning`. The plugin code already exists; only the missing rule
  made it unreachable. This is the field the regression actually took away.
- **Sampling → stays unsupported.** Enabling a field the transform drops would silently ignore the
  caller's request. An honest 400 beats a lie, and this is exactly why Codex is not OpenAI.
- **`tools` → stays unsupported.** The transform forwards a caller's array verbatim into a Responses
  payload, but the two tool shapes are not interchangeable. The installed litellm 1.87.0 proves it
  in its own converter
  (`responses/litellm_completion_transformation/transformation.py:1439-1450`): Chat Completions
  nests the definition under `function`, the Responses API expects it **flattened** next to `type`.
  Verbatim forwarding would therefore reach the wire in a shape the endpoint cannot read. Enabling
  function calling for Codex needs a shape adapter in the transform — a separate change, out of
  scope for a restoration. `tool_choice` follows `tools`; alone it is meaningless.
- **`previous_response_id` → not enabled.** `_build_payload` hardcodes `store: False`, so no
  response is ever persisted to continue from. Advertising it would be a control the gateway
  structurally cannot honor.
- **`truncation` / `include` → not enabled.** Both are carried, but no caller need is demonstrated
  and each would owe a schema, an observation and a wire test (§4.4). YAGNI; they can be added when
  something asks for them.

## Design

Two new provider-local `parameters.py` modules, mirroring the four existing ones. Each plugin
selects from `core/standard_parameters.py` — the shared *vocabulary* — and owns *which* words it
speaks. No provider names enter core; the base class gains no default rules.

Observation source labels stay provider-owned and distinct, so no provider's evidence is ever
inferred from another's: `antigravity:code-assist` and `codex:responses`. Antigravity shares the
Code Assist request shape with Gemini's OAuth path but is a different upstream with its own
settings-driven hosts, so it gets its own label rather than borrowing `gemini:code-assist`.

`reasoning_effort` reuses the shared `REASONING_EFFORT_SCHEMA` (`none|minimal|low|medium|high`)
rather than a Codex-local narrowing. Rejecting a value the provider would accept is the defect class
this campaign exists to remove; an enum value a specific model declines fails upstream with the
provider's own message, which is the milder failure.

Transport needs no work: `chat_transport_capabilities` derives `stream` from
`supports_chat_streaming()`, which both providers already answer `False`.

## Planned changes

- `plugins/antigravity_provider/parameters.py` (NEW) — 5 sampling/stop rules + `tools`
  (`tool_choice=False`), OAuth-only; tool capabilities; the labelled-static observation constant.
- `plugins/antigravity_provider/plugin.py` — `chat_parameter_rules`, `chat_parameter_tools`,
  `chat_parameter_observations`.
- `plugins/codex_provider/parameters.py` (NEW) — the `reasoning_effort` rule, OAuth-only; the
  labelled-static observation constant; no tool capabilities.
- `plugins/codex_provider/plugin.py` — `chat_parameter_rules`, `chat_parameter_observations`.
- New tests under `tests/unit/antigravity/` and `tests/unit/codex/`.

## Test plan

RED first. Every enabled field is proven in the FINAL TRANSFORMED BODY, not merely at the classifier.

Antigravity:

- Each of `temperature`, `top_p`, `max_tokens`, `stop` (both scalar and array forms) and
  `provider_params.top_k` reaches `build_generate_content_body`'s `generationConfig` under its wire
  name.
- `tools` reaches `tools[0].functionDeclarations` with the name/description/parameters preserved.
- `tool_choice`, `response_format`, `seed` and an unknown field still fail closed at classification.
- An out-of-range `temperature` and a wrong-typed `stop` item fail closed as malformed.
- The rules, the tool capabilities and the observations agree: every enabled path is evidenced.

Codex:

- Caller `reasoning_effort` survives classification and lands in the Responses payload as
  `reasoning.effort` — the assertion runs through `prepare_chat_body` into `_build_payload`.
- `temperature`, `max_tokens`, `tools` and `tool_choice` are still rejected with
  `unsupported_parameters`, before any credential access.
- An off-ladder `reasoning_effort` fails closed as malformed.
- `_build_payload` is pinned as the reason sampling is unsupported: a payload built with those keys
  present in `optional_params` does not contain them.
- Codex advertises no tool capability, so `supported_tools` stays empty.

## Acceptance

- Each enabled field dispatches and is asserted in the final transformed body.
- Unsupported fields still fail closed with `400 unsupported_parameters` before credential access.
- Summary, detail contract and dispatch agree for both providers; every enabled field carries an
  observation.
- Codex remains a distinct provider, never classified as OpenAI.
- Full aigateway gate green; no prior test weakened.

## Outcome

- **Actual files:** exactly as planned, six files.
  - `src/aigateway/plugins/antigravity_provider/parameters.py` (NEW, 123 lines)
  - `src/aigateway/plugins/antigravity_provider/plugin.py` (+36) — the three hooks
  - `src/aigateway/plugins/codex_provider/parameters.py` (NEW, 84 lines)
  - `src/aigateway/plugins/codex_provider/plugin.py` (+26) — rules + observations only
  - `tests/unit/antigravity/test_antigravity_parameter_projection.py` (NEW, 237 lines)
  - `tests/unit/codex/test_codex_parameter_projection.py` (NEW, 163 lines)
- **Commits:** `b62d4638` — *feat(aigateway): restore caller parameter support for codex and
  antigravity*; 6 files, +664. Source and tests only.
- **Gates:** `run_gates.py aigateway` ALL GREEN — ruff check · ruff format --check · pyright ·
  check_no_enterprise · pytest with `--cov=aigateway --cov-fail-under=80`. Full suite
  **1888 passed, 40 skipped**; the 39 new tests are all of the delta. No test file is modified in
  the diff (`git status` shows the two plugin modules as the only edits), so no prior test was
  weakened, deleted or skipped.
- **Verification beyond the suite:** the three surfaces were confirmed to agree from one rule
  source. `routes/model_parameters.py:143-166` composes the detail document from the same plugin
  hooks, and a direct probe of the summary row builder returns
  `codex/gpt-5.5 → supported_parameters ['reasoning_effort'], supported_tools []` and
  `antigravity/gemini-3-flash → ['max_tokens','provider_params.top_k','stop','temperature','tools','top_p'], ['function']`.

### Deviations

- **Codex ends the unit with a single enabled parameter.** The plan anticipated this, but it is
  worth restating as the headline result: `reasoning_effort` is the whole restored surface, because
  it is the only standard caller field the installed Responses transform carries to the wire. The
  narrowness is the honest report of what that endpoint accepts through this gateway, not an
  unfinished job.
- **Function calling for Codex is deferred and separately trackable.** The transform forwards a
  caller's `tools` array verbatim, but Chat Completions nests the definition under `function` while
  the Responses API expects it flattened beside `type` (the installed litellm carries its own
  converter for exactly this asymmetry). Enabling it needs a shape adapter in the transform — a new
  capability, not a restoration, and out of this unit's scope. `tool_choice` follows `tools`.
- **`chat_parameter_tools` is deliberately NOT overridden on Codex.** The base default `()` already
  says "no tool capability"; an explicit override returning `()` would read as an opt-in to nothing
  and would have to be deleted again when the adapter lands. An implementation note records the choice at
  the site.
- **Antigravity's rule set has the same shape as Gemini's**, because the two body builders are the
  same shape — but the evidence was re-derived from Antigravity's own builder and is labelled
  `antigravity:code-assist`, never borrowed from `gemini:code-assist`. If one builder changes, only
  that provider's rules move.
- **`--skip-append-only` was passed to the gate runner**, as in the preceding units of this
  campaign. The property it checks was instead established directly from the diff: every test file
  in this change is newly added, and no existing test file appears as modified.
