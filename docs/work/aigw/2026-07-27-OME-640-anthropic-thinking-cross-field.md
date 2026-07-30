---
ticket: OME-640
stack: aigateway
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-640 — Reject Anthropic reasoning/max-token combinations the model cannot serve

## Intent

Anthropic's rules validate each field alone. `reasoning_effort` and `max_tokens` are both enabled
and both schema-checked (`plugins/anthropic_provider/parameters.py:69-99`), but nothing checks them
against each other and nothing varies by model — so the gateway advertises a combination the
provider refuses.

The gap is real and narrow, and both halves of it were measured against the installed
litellm 1.87.0 rather than assumed.

## Evidence the defect is live

**1. Two of the five registered models still use MANUAL thinking.**
`AnthropicConfig._map_reasoning_effort` branches on `_is_adaptive_thinking_model(model)` *before* it
looks at the effort value, so the fleet splits cleanly:

| Registered model | `_map_reasoning_effort` for any enabled effort | Constrained? |
|---|---|---|
| `claude-opus-4-8` | `{"type":"adaptive"}` | no — no budget exists |
| `claude-opus-4-7` | `{"type":"adaptive"}` | no |
| `claude-sonnet-4-6` | `{"type":"adaptive"}` | no |
| `claude-sonnet-4-5` | `{"type":"enabled","budget_tokens":N}` | **yes** |
| `claude-haiku-4-5` | `{"type":"enabled","budget_tokens":N}` | **yes** |

The budget ladder over the gateway's own `REASONING_EFFORT_SCHEMA` enum
(`none|minimal|low|medium|high`) is `minimal→1024`, `low→1024`, `medium→2048`, `high→4096`;
`none` maps to no thinking at all. `xhigh`/`max` exist in litellm but the gateway schema rejects
them earlier, so they are out of scope.

**2. Anthropic requires `budget_tokens` < `max_tokens`.** Confirmed against the current Claude
platform documentation (*Build with Claude → Extended Thinking*): "The `budget_tokens` parameter
must be less than `max_tokens`."

**3. The gateway only produces the invalid pair when the caller sets `max_tokens`.**
`BaseConfig.update_optional_params_with_thinking_tokens` raises `max_tokens` to
`budget + DEFAULT_MAX_TOKENS` **only** when neither `max_tokens` nor `max_completion_tokens` was
supplied. Probed directly:

```
claude-sonnet-4-5  effort=high, max_tokens=128 → {"max_tokens": 128, "thinking": {"budget_tokens": 4096}}   # invalid
claude-sonnet-4-5  effort=high, no max_tokens  → {"thinking": {"budget_tokens": 4096}, "max_tokens": 8192}  # valid
claude-opus-4-8    effort=high, max_tokens=128 → {"max_tokens": 128, "thinking": {"type": "adaptive"}}      # valid
```

**4. The exemption is auth-dependent, and the split lives in the credential layer, not the
parameter layer.** Interleaved thinking lifts the constraint — the documentation is explicit that
"With interleaved thinking, the `budget_tokens` can exceed `max_tokens`" — but it is gated on the
`interleaved-thinking-2025-05-14` beta header *and* is defined as a **tool-use** feature
("extended thinking with tool use … allows Claude to think between tool calls"). In this gateway:

- `AnthropicOAuth._build_headers` (`auth.py:74-79`) sends `anthropic-beta: <settings.beta>`, which
  includes `interleaved-thinking-2025-05-14`.
- `_api_key_headers` (`plugin.py:37-41`) sends `Authorization` only — no beta header at all.

So the *same body* is legal or illegal depending on which credential resolved. The check therefore
has to read the RESOLVED auth mode, which is only known after profile/connection resolution.

## Design

A bounded, provider-owned cross-field seam, called once in `routes/chat.py` immediately after
`classify_and_project_chat_parameters` and before provider preparation, cache planning, credential
access and dispatch.

**Why a new hook rather than widening the rules.** A `ParameterProjectionRule` is per-path by
construction, and the classifier is deliberately provider-agnostic — `parameter_projection.py`
carries an explicit "no provider-name switch" invariant. A cross-field, model-specific, auth-specific
predicate cannot be expressed there without breaking that. The hook keeps core provider-agnostic and
keeps the Anthropic knowledge inside the Anthropic plugin.

**Why it raises rather than returns.** It sits directly under the classification `try` block in the
route and is the same kind of decision — a fail-closed refusal before any credential is read. A
plugin that computes a conflict cannot then have it silently discarded by a caller that ignores a
return value.

**Decision procedure** (manual-thinking model, effort mapping to budget `B`, caller/profile
`max_tokens` `M`):

- adaptive-thinking model → never conflict.
- `reasoning_effort` absent or `"none"` → no thinking → never conflict.
- `M` absent → litellm raises it above `B` → never conflict.
- otherwise conflict iff `M <= B`, **unless** exempt.
- exempt iff resolved auth mode is `oauth` **and** the model honors the interleaved beta **and** the
  body carries a non-empty `tools` array.

`claude-haiku-4-5` is deliberately NOT exempt. The published documentation is indeterminate here —
it groups Opus 4.5 and Haiku 4.5 as having "different interleaved thinking behaviors" without saying
what they are — so this follows the approved matrix and takes the fail-closed reading. The cost of
being wrong in this direction is a visible, actionable 400 on a combination that is invalid on the
api-key path anyway; the cost of the other direction is an opaque provider error.

**Response.** A distinct additive code `incompatible_parameters` (400), naming the conflicting
request paths and stating the constraint. Reusing `unsupported_parameters` would be wrong: every
named field IS enabled and DID validate — it is the combination the provider refuses, and the caller
would go looking for a disabled field that does not exist.

**Profile-default attribution.** `max_tokens` can arrive from a stored profile default (OME-638), so
the operator-channel `logger.warning` established there also fires when a conflicting path came from
the defaults. Only one caller-facing code is needed: `reasoning_effort` is opted out of profile
defaulting by `AnthropicProviderPlugin.should_apply_profile_default`, so on this provider at least
one side of the conflict is always the caller's own field, and the caller can fix either side (body
wins per field).

## Planned changes

- `core/parameter_projection.py` — add `IncompatibleParametersError`, sibling to
  `UnsupportedParametersError`; carries safe request paths plus a caller-actionable reason.
- `core/plugin_base.py` — new `validate_chat_parameter_combination(body, *, model, auth_mode)` hook,
  default no-op.
- `plugins/anthropic_provider/thinking.py` (NEW) — the manual-thinking model set, the effort→budget
  ladder, the interleaved-beta model set, and the decision procedure.
- `plugins/anthropic_provider/plugin.py` — implement the hook.
- `routes/chat.py` — call the hook after classification; render `incompatible_parameters`; log the
  operator channel when a profile default participates.
- New tests under `tests/unit/`.

## Test plan

RED first. Route-level tests through the real classifier and the real Anthropic rules, plus a
characterization test that runs the INSTALLED transform.

- `claude-sonnet-4-5`, api_key, `reasoning_effort="high"` + `max_tokens=128` → 400
  `incompatible_parameters` naming both fields.
- Same body on `claude-opus-4-8` / `claude-opus-4-7` / `claude-sonnet-4-6` → dispatches; the
  adaptive models are never constrained.
- `claude-haiku-4-5`, OAuth, same body **with** tools → still 400 (no exemption).
- `claude-sonnet-4-5`, OAuth, same body **with** a non-empty `tools` array → dispatches.
- `claude-sonnet-4-5`, OAuth, same body **without** tools → 400 (the beta alone is not enough).
- Boundary: `max_tokens == budget` → 400; `max_tokens == budget + 1` → dispatches.
- `reasoning_effort="none"` and `reasoning_effort` absent → never conflict, at any `max_tokens`.
- `max_tokens` absent → never conflict (litellm raises it).
- Ordering: the refusal precedes `prepare_chat_body` (tripwire) and precedes credential access
  (authenticated profile with no stored blob → a 400 rather than a 401 proves no credential read).
- A conflicting `max_tokens` supplied by a PROFILE DEFAULT still refuses, and names the profile in
  the operator log.
- Characterization: for all five registered models, the installed transform's
  `_map_reasoning_effort` output matches the module's table exactly — so a litellm upgrade that
  changes the mapping turns the gate red.
- Pinning: the Anthropic rules for `reasoning_effort`, `max_tokens` and `tools` all project to a
  target equal to their request path, which is what lets the seam read the projected body.
- Every other provider keeps the default no-op hook.

## Acceptance

- A provider-invalid reasoning/max-token combination is refused with HTTP 400 before any credential
  is read.
- Adaptive-thinking models and the exempt OAuth+tools combination dispatch unchanged.
- No provider name appears in core.
- Full aigateway gate green; no prior test weakened.

## Outcome

- **Actual files:** exactly as planned, plus one approved prior-test fixture change.
  - `src/aigateway/core/parameter_projection.py` — `IncompatibleParametersError` (+19).
  - `src/aigateway/core/plugin_base.py` — `validate_chat_parameter_combination` default no-op (+29).
  - `src/aigateway/plugins/anthropic_provider/thinking.py` — NEW, 117 lines: the manual-thinking
    model set, the effort→budget ladder, the interleaved-beta model set, `raise_on_thinking_conflict`.
  - `src/aigateway/plugins/anthropic_provider/plugin.py` — implements the hook (+12).
  - `src/aigateway/routes/chat.py` — calls the seam after classification, renders
    `incompatible_parameters` (400), logs the operator channel on a participating default (+31).
  - `tests/unit/anthropic/test_anthropic_thinking_conflict.py` — NEW, 23 tests.
  - `tests/unit/core/test_parameter_combination_seam.py` — NEW, 6 tests.
  - `tests/unit/test_chat_x_profile.py` — MODIFIED (see Deviations).

- **Commit:** `ce49ffe1` — `fix(aigateway): reject Anthropic reasoning and max-token pairs the
  model cannot serve` (`Refs: OME-640, OME-479`). Source and tests only.

- **Gates:** `uv run .claude/scripts/run_gates.py aigateway --skip-append-only` — all green.
  ruff check ✓ · ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ ·
  pytest **1990 passed, 40 skipped**, coverage **92.10%** (floor 80%). `routes/chat.py` 100%.
  Four gate rounds: (1) format diff on the two new files, (2) pyright — the two new test helpers
  took `str` where `AuthType`/`AuthMode` literals are required, (3) the prior-test collision below,
  (4) green.

- **Deviations:**
  1. **One prior test was changed, with explicit owner approval.**
     `tests/unit/test_chat_x_profile.py::test_chat_merges_profile_defaults` seeded
     `ProfileDefaults(max_tokens=4096, …)` and sent `reasoning_effort="high"` on
     `claude-haiku-4-5`. The installed litellm turns that into
     `{"max_tokens": 4096, "thinking": {"type": "enabled", "budget_tokens": 4096}}` — probed
     directly — which violates the strict `budget_tokens < max_tokens` requirement. The new check
     is therefore correct and the old fixture sat exactly on the boundary while testing something
     else entirely (default merging, body-wins-per-field). Resolution: the profile default moved to
     `8192` and its assertion to `== 8192`. No assertion was removed, relaxed, or skipped;
     `reasoning_effort="high"` was kept so the body-overrides-profile coverage is unchanged. The
     equality boundary now has its own dedicated test
     (`test_max_tokens_equal_to_the_budget_is_refused`), and both sides carry an implementation note
     pointing at each other.
  2. **Two rejected alternatives**, both declined as fail-open: relaxing the comparison to
     `max_tokens >= budget` (would forward a body we have direct evidence Anthropic rejects), and
     skipping the check when one half came from a profile default (would make identical wire bodies
     legal or illegal based on provenance).
  3. `core/plugin_base.py` is now ~575 lines, over the 450-line guideline. Not split in this unit —
     it is a pure interface surface and splitting it is a separate, wide-blast-radius change.

- **Acceptance:** met.
  - Refusal precedes credential access — proved by an authenticated profile with no stored blob
    returning 400 rather than 401 — and precedes `prepare_chat_body` via a patch tripwire.
  - All three adaptive models dispatch the identical body; the OAuth+tools exemption dispatches and
    the beta header is asserted present on that path.
  - No provider name in core: the seam is a default no-op on `ProviderPluginBase`, and a test
    asserts Anthropic is the *only* loaded plugin that overrides it.
  - The budget ladder is pinned by a characterization test over all five registered models against
    the installed transform, so a litellm upgrade that changes the mapping turns the gate red
    instead of drifting silently.
