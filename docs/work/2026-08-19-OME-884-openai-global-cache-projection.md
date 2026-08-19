---
ticket: OME-884
stack: aigateway
status: done
started: 2026-08-19
finished: 2026-08-19
---

# OME-884 — direct OpenAI global exact-response cache projection

## Intent

Make direct `openai/*` non-streaming Chat Completions eligible for AIGateway's global
exact-request cache (OME-305), so a benchmark suite re-running identical calls — including from a
second account — is answered from stored responses instead of a second paid dispatch. In the same
increment, demote `OpenAIPluginSettings.default_models` from a dispatch/cache allowlist to the
bootstrap `/v1/models` catalog it was always meant to be, so any syntactically valid `openai/*`
model can dispatch and cache.

Artifacts: `docs/tasks/2026-08-19-OME-884-…`, `docs/spec/2026-08-19-OME-884-…`,
`docs/plan/2026-08-19-OME-884-…`.

## Deviations authorized up front

- **Current shared checkout, no worktree.** The owner explicitly authorized implementing OME-884
  in the existing `OME-884-openai-global-cache-projection` checkout and directed that no worktree
  be created (this departs from CLAUDE.md D5). Unrelated modified, staged, untracked and stashed
  state in this checkout must be preserved exactly; no `git add`/`commit`/`push`/`stash`/`reset`/
  `checkout`/`restore`/`clean` or branch change is performed by this unit.
- **Seven prior OME-864 assertions change.** Their product contract is intentionally replaced by
  this MVP (listed under Test plan). Every one becomes a positive replacement, never a deletion or
  a weakening. `run_gates.py` is run normally first to record the expected append-only policy
  failure, then rerun with `--skip-append-only` for the actual gate result.

## Planned changes

Production:

- `apps/aigateway/src/aigateway/core/plugin_base/_provider.py` — model-aware participation port.
- `apps/aigateway/src/aigateway/core/request_cache/global_plan.py` — pass the raw requested model.
- `apps/aigateway/src/aigateway/plugins/openrouter_provider/plugin.py` — mechanical signature
  adaptation, behaviour unchanged.
- `apps/aigateway/src/aigateway/plugins/openai_provider/global_cache.py` — NEW: pure projection
  and adapter revision ONLY. The shared unsafe-runtime-state predicate deliberately does NOT live
  here and is owned by `plugin.py`: it reads `os.environ` and LiteLLM process globals, and this
  module must stay pure enough for the registry-wide projection-purity sweep.
- `apps/aigateway/src/aigateway/plugins/openai_provider/settings.py` — shared pure model-ID
  predicate; `validation_model` loses its `default_models` membership requirement.
- `apps/aigateway/src/aigateway/plugins/openai_provider/api_key_validation.py` — readiness model
  validated by syntax, not catalog membership.
- `apps/aigateway/src/aigateway/plugins/openai_provider/plugin.py` — catalog-independent
  `prepare_chat_body`, projection/participation hooks, shared runtime guard, no-op cache-reference
  mapper.
- `apps/aigateway/src/aigateway/plugins/openai_provider/parameters.py` — `max_tokens` keyed, rule
  revision bumped.

Tests:

- NEW `apps/aigateway/tests/unit/openai/test_openai_global_cache_projection.py`.
- `apps/aigateway/tests/unit/openai/test_openai_provider.py`,
  `test_openai_dispatch.py`, `test_openai_gateway_acceptance.py`,
  `test_openai_api_key_validation.py` — additions plus the seven authorized replacements.
- `apps/aigateway/tests/unit/test_global_cache_plan.py`,
  `tests/unit/openrouter/test_openrouter_global_cache_projection.py`,
  `tests/unit/openrouter/test_openrouter_routing_policy_routes.py` — participation signature.

No schema, migration, dependency, lockfile, route-order or persistence change. Stack rule S1 does
not apply: no model or schema is touched.

## Test plan

RED first, in four units.

1. **Pure projection and model-ID contract** — determinism, no body mutation, malformed and
   non-OpenAI bypass, default and unlisted custom models project identically apart from the model,
   JSON-safe `prepared` plus successful key construction, adapter-revision isolation, present vs
   absent top-level `system` keying differently, and a route-valid `validation_model` outside the
   catalog.
2. **Participation, dispatch refusal, hit safety** — the port receives the raw model; an ambient
   alias bypasses and refuses only its exact model while an unrelated model still participates and
   dispatches; non-empty `OpenAIConfig`, experimental handler true, a configured secret manager and
   the OME-864 unsafe globals disable both; the flag helper is total for `None` and matches
   installed LiteLLM semantics; a fill-then-poison tripwire keeps the row but refuses replay; a hit
   performs no OpenAI credential read/decrypt, auth resolution, validation, key injection or
   dispatch, while the `aigateway:index` profile read stays allowed; caller opt-out bypasses; a hit
   emits no mapper warning and reports accounting-not-supported.
3. **Keyed parameter contract** — default and unlisted route-valid models publish keyed
   `max_tokens`; equal effective values give equal plans and keys; different models or values give
   different keys; the rule covers every available auth mode.
4. **Catalog-independent route behaviour** — default and custom `miss -> hit` with one dispatch and
   one row; no collision across models or `max_tokens`; catalog removal hides the listing but keeps
   direct calls and replay; malformed model does no cache I/O; a valid-but-unsupported model misses,
   reaches a mocked OpenAI rejection and stores nothing; profile-default `max_tokens` isolates while
   equivalent explicit/default values share; differing `system_prompt` defaults isolate; exact
   replay across two accounts; Codex and OpenRouter unchanged. Dispatch proof stays in three layers
   — captured `litellm.acompletion` kwargs, `AsyncOpenAI`/httpx construction, and a `MockTransport`
   final wire covering all fourteen default models' token-field mapping.

Authorized prior-assertion replacements (seven, all positive):

1. `test_openai_provider.py` — canonical `max_tokens` `bypass` -> `keyed`.
2. `test_openai_provider.py` — inherited `CacheBypass` -> a real projection.
3. `test_openai_gateway_acceptance.py` — published parameter contract -> `keyed`.
4. `test_openai_dispatch.py` — a syntactically valid unlisted model is forwarded, not rejected.
5. `test_openai_gateway_acceptance.py` — pre-credential unregistered-model rejection replaced by
   malformed-ID and provider-rejection coverage.
6. `test_openai_provider.py` — `validation_model` need not appear in the bootstrap catalog.
7. `test_openai_api_key_validation.py` — a route-valid validation model outside `default_models` is
   probed rather than treated as locally misconfigured.

Authorized TEST-ISOLATION fixes (two, review cycle 1 — deliberately recorded SEPARATELY from the
seven contract replacements above, because they change no product contract and assert no new
behaviour of the system under test; they only stop a prior test from corrupting shared state):

A. `test_openai_persistence.py::test_chat_selects_openai_api_key_connection_by_label`
B. `test_openai_persistence.py::test_chat_selects_named_openai_profile`

   Both replaced `monkeypatch.setattr(plugin, "chat_completion", capture)` — on the module-level
   `PLUGIN` singleton — with a scoped `unittest.mock.patch.object(...)` context, and each now
   asserts `"chat_completion" not in vars(plugin)` afterwards. Every pre-existing assertion in both
   tests is preserved verbatim; the only other change is dropping the `monkeypatch` fixture from the
   two signatures, which those tests no longer use. Owner-authorized in review cycle 1.

## Acceptance

- Identical eligible `openai/*` requests produce `miss -> hit`; different models, messages, system
  content or effective `max_tokens` never collide.
- An unlisted route-valid custom model caches exactly like a seeded one; catalog removal affects
  `/v1/models` only.
- The projection is total, deterministic, non-mutating, JSON-safe, identity-free, credential-free,
  settings-free and I/O-free.
- Unsafe ambient OpenAI/LiteLLM state and an exact-model ambient alias fail closed in both
  participation and dispatch; unrelated aliases do not.
- A hit performs no OpenAI provider-credential work and no dispatch, and emits truthful metadata.
- Codex, Anthropic and OpenRouter behaviour is unchanged; no schema, migration, dependency or
  route-order change exists.
- Focused tests plus the complete AIGateway gate (`--skip-append-only` after the recorded policy
  failure) pass; new production files stay at or under 450 lines.

## Outcome

- **Baseline gate:** `uv run .claude/scripts/run_gates.py aigateway` fails ONLY on the append-only
  check, naming exactly five files and exactly the authorized regions:
  `test_openai_api_key_validation.py` (lines 238, 242), `test_openai_dispatch.py` (167-175),
  `test_openai_gateway_acceptance.py` (60, 73), `test_openai_provider.py` (82, 93, 106, 119-123),
  `test_global_cache_plan.py` (445, 454). Re-run after the last fix produced the identical list —
  the flagged set never grew. Every region is one of the seven authorized replacements or the
  mechanical `participates_in_global_cache` signature adaptation; none is a deletion or a
  weakening, and each carries an `OME-884 (authorized contract change)` comment stating the old
  contract and why it changed.

- **Actual files** (matches Planned changes exactly; no unplanned file touched):

  Production — modified:
  - `apps/aigateway/src/aigateway/core/plugin_base/_provider.py`
  - `apps/aigateway/src/aigateway/core/request_cache/global_plan.py`
  - `apps/aigateway/src/aigateway/plugins/openrouter_provider/plugin.py`
  - `apps/aigateway/src/aigateway/plugins/openai_provider/plugin.py` (327 lines)
  - `apps/aigateway/src/aigateway/plugins/openai_provider/settings.py` (133 lines)
  - `apps/aigateway/src/aigateway/plugins/openai_provider/api_key_validation.py` (220 lines)
  - `apps/aigateway/src/aigateway/plugins/openai_provider/parameters.py` (54 lines)

  Production — new:
  - `apps/aigateway/src/aigateway/plugins/openai_provider/global_cache.py` (135 lines)

  Tests — modified:
  - `apps/aigateway/tests/unit/openai/test_openai_provider.py`
  - `apps/aigateway/tests/unit/openai/test_openai_dispatch.py`
  - `apps/aigateway/tests/unit/openai/test_openai_gateway_acceptance.py`
  - `apps/aigateway/tests/unit/openai/test_openai_api_key_validation.py`
  - `apps/aigateway/tests/unit/test_global_cache_plan.py`

  Tests — new:
  - `apps/aigateway/tests/unit/openai/test_openai_global_cache_projection.py` (593 lines)
  - `apps/aigateway/tests/unit/openai/test_openai_route_global_cache.py` (607 lines)

  Every new production file is at or under 450 lines. No schema, migration, dependency, lockfile,
  route-order or persistence change; `routes/chat.py` and `routes/chat_cache_stage.py` untouched.
  Stack rule S1 does not apply — no model or schema was touched.

- **Commit:** this OME-884 implementation commit (`feat(aigateway): cache direct OpenAI responses`;
  `Refs: OME-884`). Nothing was pushed or stashed; `git stash list` is unchanged (3 pre-existing
  entries). The staged deletion of `web/.gitignore` and the unrelated modifications to
  `.claude/commands/asana.md` and `.claude/skills/working-in-this-repo/SKILL.md` remain outside this
  commit exactly as found.

- **Gates:** `uv run .claude/scripts/run_gates.py aigateway --skip-append-only` — **ALL GATES
  GREEN**: `ruff check`, `ruff format --check`, `pyright` (0 errors),
  `scripts/check_no_enterprise.py`, `pytest --cov=aigateway --cov-fail-under=80 -q`.
  Focused runs during the loop: `tests/unit/openai` 175 passed; the combined
  openai + openrouter + every global-cache suite 1228 passed.

  Three gate failures were fixed in the code, never in the gate:
  1. `PLR0911` — `_has_unsafe_openai_runtime_state` had 9 returns. The eight near-identical
     truthiness branches were collapsed into one `_LITELLM_GLOBAL_TRUTHY_FIELDS` tuple; the ceiling
     was a fair signal that a list was pretending to be control flow. Verdict unchanged
     (`proxy_auth` deliberately keeps its `is not None` test, which is not truthiness).
  2. `E501`/format in the new projection test — three long lines wrapped, one file reformatted.
  3. `pyright` — `raised.value.detail["code"]` on a `starlette` `HTTPException` (whose `detail` is
     inferred `str`). Replaced with the file's existing whole-dict equality assertion, which is
     also the stronger check.

- **Deviations:**
  1. **No worktree, current checkout** — authorized up front (see above). Preserved: unrelated
     modified/staged/untracked files and all three stashes.
  2. **Seven prior-assertion replacements** — authorized up front; all applied positively, and the
     append-only gate output above is the evidence that nothing beyond them changed.
  3. **Route tests placed in a NEW file** rather than appended to
     `test_openai_gateway_acceptance.py` as the plan's file list said. That file owns the catalog
     and pre-credential-rejection contract; the route cache suite is a separate responsibility and
     would have pushed it far past the 450-line guidance. Content is exactly what the plan
     specified for Unit 4.
  4. **Units 2-4 were not strictly RED-first.** The Unit 2 guard tests, the fourteen-model wire
     matrix and all thirteen Unit 4 route tests were written after the code they exercise (Unit 4
     required no production change at all — the route already called the hooks). Their non-vacuity
     was established by explicit observed tripwires instead of by a RED run:
     - stripping the three new dispatch refusals and the alias half from `plugin.py` → exactly 8
       tests failed; restored and re-verified byte-identical.
     - forcing `project_global_cache_request` to return `CacheBypass` unconditionally → 12 of the
       13 route tests failed.
     - relaxing `is_route_valid_model_id` to a bare prefix check → the 13th (the malformed-model
       test, which is a bypass either way) failed.
  5. **A pre-existing test-isolation defect was found and worked around, not fixed.**
     `tests/unit/openai/test_openai_persistence.py` calls
     `monkeypatch.setattr(plugin, "chat_completion", …)` on the module-level `PLUGIN` singleton.
     pytest reads the old value with `getattr` (which resolves through the class) and restores it
     with `setattr`, so it permanently leaves the original BOUND METHOD as an instance attribute,
     shadowing any later class-level patch. Verified with a throwaway two-test probe. This made the
     new route tests pass alone and fail 401 when run after that file. Fixed on my side only — the
     new suite patches the plugin INSTANCE the app dispatches through via `mock.patch.object`,
     which restores correctly — because repairing the prior test would itself be an unauthorized
     append-only violation. **Recommend a follow-up ticket** to convert that call site.

## Review cycle 1 — owner findings addressed

1. **The ambient-state guard was not total (real defect, reproduced first).** A direct probe
   confirmed the report: with `litellm.OpenAIConfig.get_config` raising,
   `PLUGIN.participates_in_global_cache(...)` and `PLUGIN.chat_completion(...)` both propagated
   `RuntimeError` instead of standing down. Every ambient read was defensive about a MISSING
   attribute but not about one that answers BY RAISING — `get_config()` is a call, `model in
   aliases` runs a hostile `__contains__`, and `bool(...)` runs a hostile `__bool__`.

   Fixed by making `_has_unsafe_litellm_global_state` total: one `try/except Exception` at the
   single junction both readers pass through, returning "unsafe" and logging a warning.
   `BaseException` is deliberately not caught. Chose one guard there rather than eight per-read
   guards — it makes both callers total at once and keeps the two verdicts structurally incapable
   of diverging.

   Impact that was NOT previously visible: the two paths degraded differently. The cache stage
   absorbed the exception into `build_global_cache_plan`'s catch-all and published this provider's
   *projection* bypass for something that was never a projection decision, while dispatch surfaced
   a generic 502 `provider_error` — blaming OpenAI for a runtime the gateway could not certify.
   Both now produce the documented outcomes: participation `False`, and a sanitized non-retryable
   503 `unsafe_openai_environment` raised before any client construction.

   RED-first: 7 new tests (4 participation cases in `test_openai_global_cache_projection.py`,
   3 dispatch cases in `test_openai_dispatch.py`) covering a raising `get_config`, a raising alias
   `__contains__`, and a raising `__bool__` on `headers` and on `callbacks`. All 7 observed failing
   with the escaping `RuntimeError` before the fix, all passing after. The reviewer's original
   probe was re-run and now reports `participation -> False` and the 503.

   Also corrected in the same pass: `_has_unsafe_openai_runtime_state`'s docstring still claimed
   "never raise", which after the fix is only true via its caller. That stale claim is now an
   explicit `AIDEV-NOTE` saying where totality is actually enforced and why a second `try/except`
   must not be added — the same class of misleading comment this review cycle was opened to catch.

2. **Singleton test contamination fixed at its source, not deferred.** See "Authorized
   TEST-ISOLATION fixes" above for the two edits. Verified: the persistence suite followed by a
   probe asserting `"chat_completion" not in vars(PLUGIN)` now passes, where it previously failed.
   The `_dispatching()` helper in `test_openai_route_global_cache.py` keeps `patch.object` on the
   registry's instance — that is independently the correct target, since it is the object the route
   actually calls — but its commentary no longer describes the contamination as unresolved.

3. **Durable docs reconciled with the implementation.**
   - `docs/spec/…` : `resolved_model` now correctly documented as the UPSTREAM id
     (`openai/gpt-5.6-sol` -> `gpt-5.6-sol`), matching the implementation, the OpenRouter
     convention, and the final HTTP payload pinned in `test_openai_dispatch`. Also notes that the
     caller's prefixed string is not lost — the core keys it separately as `requested_model`.
   - This ledger: the unsafe-runtime predicate is owned by `plugin.py`, NOT `global_cache.py`
     (it reads `os.environ` and LiteLLM globals, so it cannot live in the module the
     projection-purity sweep polices).

4. **OpenRouter widened-port coverage completed — by ADDITION rather than replacement.**
   `tests/unit/openrouter/test_openrouter_global_cache_projection.py` gains
   `test_the_operator_switch_is_the_whole_answer_whatever_model_is_passed`, which drives the
   enabled and disabled plugins through `participates_in_global_cache(model)` with a raw model, an
   `:online` model, another provider's model, an empty string, and non-string values, and asserts
   the defaulted and explicit forms agree.

   **Deviation from the literal instruction, stated plainly:** the request was to change the two
   existing assertions to pass a raw model. I appended instead, leaving
   `test_a_disabled_provider_declines_to_participate_in_the_shared_cache` untouched. Rewriting it
   would have DELETED the suite's only coverage of the DEFAULTED call — the form the base-class
   port documents and that `ProviderPluginBase` relies on — trading one form of coverage for
   another rather than gaining it. Appending also spends no further append-only exception. The
   stated goal ("prove behaviour remains unchanged under the widened port") is met in full; if you
   would rather the prior assertions be rewritten in place, say so and I will.

### Checks re-run this cycle

- Focused: `tests/unit/openai tests/unit/openrouter` + every global-cache suite
  (`test_global_cache_plan`, `test_global_cache_registry_conformance`,
  `test_global_cache_projection_purity`, `test_chat_global_cache_route`,
  `test_chat_global_cache_effective_request`, `test_global_cache_key`, `test_chat_request_cache`) —
  **1236 passed**.
- Normal gate (`run_gates.py aigateway`) — fails ONLY the append-only check, now naming SIX files.
  The sixth is `test_openai_persistence.py` (lines 201-204, 237-247, 283, 312-322), which is
  exactly the two authorized test-isolation fixes plus their two now-unused fixture parameters and
  nothing else — confirmed by reading the file's full diff. The other five entries are byte-for-byte
  the same regions reported in the previous cycle.
- `run_gates.py aigateway --skip-append-only` — **ALL GATES GREEN** (ruff, ruff format, pyright 0
  errors, check_no_enterprise, pytest with `--cov-fail-under=80`).
- `git diff --check` — clean. `plugin.py` is 366 lines, still under the 450 limit.
- The owner authorized the implementation commit after review. Nothing was pushed, stashed or
  rebased; no branch change; unrelated worktree state (`.claude/commands/asana.md`,
  `.claude/skills/working-in-this-repo/SKILL.md`, the staged `web/.gitignore` deletion, all untracked
  files, all three stashes) remains exactly as found.
