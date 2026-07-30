---
ticket: OME-638
stack: aigateway
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-638 — Validate profile defaults against the provider parameter rules before dispatch

## Intent

Stored profile defaults reach the provider without passing the parameter contract.

`routes/chat.py:118` classifies the caller body against the provider rule set; `_apply_defaults`
(`routes/chat_credentials.py:285`) merges the profile defaults **afterwards**, at
`routes/chat.py:137`, inside the same expression that calls `prepare_chat_body`. Every field it
injects therefore skips the rule check, the schema check and the auth-mode check that the identical
caller-supplied field must pass — and skips them on the wrong side of provider preparation, cache
planning, credential access and dispatch.

Three of the six `ProfileDefaults` fields are optional model parameters and are affected:
`max_tokens`, `temperature`, `reasoning_effort`. The other three are structural — `model`,
`system_prompt` (→ `messages`) and `timeout_seconds` (→ `timeout`) all resolve to members of
`GATEWAY_OWNED_FIELDS`, which the classifier authorizes structurally and which need no rule.

That split is derived, not asserted: `parameter_projection.GATEWAY_OWNED_FIELDS` already documents
itself as "the single source of *not an optional model parameter*", so this unit reads it rather
than introducing a second list that could drift from it.

## Evidence the defect is live

- **Enabled-set bypass.** Codex enables exactly one field, `reasoning_effort` (OME-634). A caller
  sending `temperature` to Codex gets a 400. A profile *default* `temperature` is merged after
  classification, so it reaches `_build_payload`, which drops it silently. Same field, same
  provider, two answers — and the silent one is the operator-configured path.
- **Schema bypass.** Anthropic's real `temperature` range is `[0, 1]`, narrower than the shared
  `[0, 2]` schema (OME-579). A stored default of `1.5` is refused from a caller and accepted from a
  profile.
- **Ordering.** Even a default that is ultimately harmless is merged after the point where the
  route has already committed to a cache plan input and is about to read a credential.

## Design

Merge the defaults into the caller body **before** classification. One classification pass, one
projection, one rule set — a stored default is authorized exactly like a caller value, and there is
no second validation path that can drift from the first.

**Why merge-then-classify rather than classify-defaults-separately.** The classifier returns a
*fresh projected* body: accepted values sit at their rule target, which need not equal the request
path (`provider_params.top_k` → `extra_body.top_k`). Validating defaults in a separate pass would
produce a second projected body that then has to be deep-merged into the first at target level,
leaf by leaf, to preserve "body wins per field". Merging at the *request-path* level before
classification avoids that machinery entirely and is strictly more faithful: the default is
projected by the very same rule that projects a caller value.

**Provenance.** "Body wins per field" is not just preserved, it is what makes the outcome
attributable: a default can only occupy a request path the caller omitted. So `_apply_defaults`
returns the set of paths it injected, and any rejection at one of those paths is known to come from
the stored profile rather than from the request.

**Two error codes.** A rejection caused solely by stored defaults is reported as
`invalid_profile_defaults`, naming the profile; a caller-supplied rejection stays
`unsupported_parameters`. Reporting an operator-configuration fault under the caller-parameter code
would send the caller looking for a field that is not in their request. Caller faults keep
precedence when both are present — the request must be fixed either way. Status stays **400**,
matching the existing `api_key_not_supported` precedent in `_inject_credentials` for stored
configuration a provider cannot serve.

**Placement.** The merge goes after `plugin.strip_provider_dispatch_controls(body)` and before
classification, so the control-plane strips continue to see caller input only. `ProfileDefaults` is
a closed pydantic model of six typed fields, none of which is a dispatch control, so nothing is
lost by keeping defaults out of the strips.

## Planned changes

- `routes/chat_credentials.py` — `_apply_defaults` returns `(body, injected_paths)`. Behavior of the
  merge itself is unchanged, including the `should_apply_profile_default` opt-out and the
  `timeout_seconds` → `timeout` rename.
- `routes/chat.py` — apply defaults before `classify_and_project_chat_parameters`; render the
  rejection through a new module-level helper that attributes it to the caller or to the profile.
- New tests in `tests/unit/` covering both attribution arms, the ordering claim, and the
  still-working valid-default path.

## Test plan

RED first. Route-level tests through the real classifier and real provider rule sets, so the
evidence is the shipped contract rather than a stub.

- Codex profile default `temperature` → 400 `invalid_profile_defaults` (no enabled rule), not a
  silent drop.
- Anthropic profile default `temperature=1.5` → 400 `invalid_profile_defaults` (fails the
  provider-narrowed `[0, 1]` schema), while `0.5` is accepted and dispatched.
- Caller sends an unknown field **and** the profile holds a bad default → `unsupported_parameters`
  wins; the caller-facing code never blames the profile for the caller's own field.
- **Ordering:** with the plugin's `prepare_chat_body` replaced by a tripwire, a bad default still
  returns 400. `prepare_chat_body` is the earliest of the four downstream steps
  (`chat.py:137` < cache plan `:141` < credential injection `:160` < dispatch `:196`), so one
  assertion establishes the whole "before provider preparation, cache planning, credential access
  and dispatch" claim.
- A valid default that a transform renames downstream still reaches the wire: Codex
  `reasoning_effort` default still arrives as `reasoning.effort`.
- Structural defaults unchanged: `system_prompt` still prepends a system message,
  `timeout_seconds` still becomes `timeout`, and neither needs a rule.
- Unit-level: `_apply_defaults` reports exactly the paths it injected — empty when the body already
  carries the field, empty when the provider opts out via `should_apply_profile_default`.
- Unit-level: the attribution helper picks the right code for caller-only, profile-only, and mixed
  rejection sets.

## Acceptance

- A profile default is refused when the provider has no enabled rule for it, when the value fails
  the provider's schema, or when the rule does not apply to the resolved auth mode.
- The refusal precedes provider preparation, cache planning, credential access and dispatch.
- Attribution is correct in both directions.
- A valid default still merges, projects and dispatches unchanged.
- Full aigateway gate green; no prior test weakened.

## Outcome

- **Actual files:** 3 paths — 1 new, 2 modified. Matches the plan.
  - `src/aigateway/routes/chat_credentials.py` — `_apply_defaults` now returns
    `(body, frozenset[str])`, the request paths it wrote. The merge itself is byte-for-byte the
    same decision procedure: `should_apply_profile_default` opt-out, `timeout_seconds` → `timeout`,
    body-wins-per-field.
  - `src/aigateway/routes/chat.py` — defaults merge moved ahead of
    `classify_and_project_chat_parameters`; new module-level `_parameter_rejection_exception`
    attributes the failure; an operator-channel `logger.warning` fires whenever any default path is
    rejected, including the case where a caller fault outranks it in the response.
  - `tests/unit/test_chat_profile_default_validation.py` (NEW, 473 lines, 14 tests).
- **Commits:** `b9f2706b` — *fix(aigateway): validate profile defaults against the provider rules*;
  3 files, +589/-22. Source and tests only.
- **Gates:** `run_gates.py aigateway --skip-append-only` ALL GREEN on the second attempt — ruff
  check · ruff format --check · pyright · check_no_enterprise · pytest with
  `--cov=aigateway --cov-fail-under=80`. One red round, not a logic change: an `E501` on a
  dotted-path test constant, fixed by splitting the plugin prefix into its own constant.
  Full suite **1941 passed, 40 skipped** — 1927 before, so the 14 new tests are the entire delta
  and no prior test changed behavior. No prior test file was modified, deleted or skipped, which is
  the direct proof for `--skip-append-only` (`git status` showed only the two source paths and the
  one new test file).
- **No schema or model change**, so stack rule S1 (migration ships with the schema) does not apply.
- **Zero `# type: ignore` added.**

### Measured blast radius

A registry sweep of the three defaultable model parameters against each provider's enabled rules
under its own auth modes:

| Provider | Accepted as a default | Newly refused | Plugin opts out |
|---|---|---|---|
| anthropic | temperature, max_tokens, reasoning_effort | — | reasoning_effort |
| ollama | temperature, max_tokens, reasoning_effort | — | — |
| antigravity | temperature, max_tokens | reasoning_effort | — |
| gemini-cli | temperature, max_tokens | reasoning_effort | — |
| huggingface | temperature, max_tokens | reasoning_effort | — |
| openrouter | temperature, max_tokens | reasoning_effort | — |
| codex | reasoning_effort | temperature, max_tokens | — |

**No provider loses a working capability**, which was checked rather than assumed:

- anthropic and ollama enable all three, so nothing changes; anthropic additionally opts
  `reasoning_effort` out of profile defaulting already.
- On codex, antigravity and gemini-cli the newly-refused field was being **discarded by the
  provider transform** — the request "succeeded" while ignoring the operator's setting. A silent
  no-op becomes a visible, actionable error.
- On openrouter and huggingface the newly-refused field already made the request **fail at
  dispatch**: the installed litellm 1.87.0 transform raises `UnsupportedParamsError` for
  `reasoning_effort` on both. The same request still fails — earlier, without reading a credential
  or doing cache work, and with a message that names the profile instead of a provider-shaped
  error.

So the change converts unauthorized defaults from "silently ignored" or "fails late and opaquely"
into "fails immediately and says which profile". Nothing that worked stops working.

### Deviations

- **A second error code was added to the chat contract.** The plan anticipated it and the reasoning
  is recorded under Design, but it is an addition to a public API surface and is called out here:
  `invalid_profile_defaults` (400) now joins `unsupported_parameters` (400). It is purely additive —
  no existing code, status or payload shape changed.
- **`unsupported_parameters` now reports only caller-supplied paths.** In principle a narrowing of
  an existing response; in practice not observable, because before this unit profile defaults were
  never classified and so could never have appeared in that map. Verified by the unchanged full
  suite.
- **`messages` is included in the reported write set** even though the system-prompt default
  rewrites an existing gateway-owned field rather than adding a new one. Keeping it exact costs
  nothing and avoids a future duplicate-channel rejection on `messages` being blamed on the caller.
- **One theoretical attribution gap, documented rather than engineered around.** If a provider rule
  set addressed the same target from both a caller path and a default path, the resulting
  `duplicate_channel` rejection would name whichever path projected second — the default, since
  defaults are appended last. That configuration is already rejected as a provider-config defect by
  the wrapper-path agreement work (OME-599), so no machinery was added for it.
- **`--skip-append-only` was passed**, as in the preceding units, with the property established
  directly from the diff: no existing test file appears as modified or deleted.
