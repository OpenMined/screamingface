---
ticket: OME-704
stack: aigateway
status: done
started: 2026-07-30
finished: 2026-07-30
---

# OME-704 — Validated OpenRouter price and privacy routing controls per request

## Intent

Let an authenticated researcher constrain an OpenRouter chat request by unit price and
downstream data policy without ever receiving access to OpenRouter's raw `provider` routing
control plane. Five caller-visible leaves under the existing `provider_params` wrapper
(`sort`, `max_price_prompt`, `max_price_completion`, `data_collection`, `zdr`) express four
logical OpenRouter controls; AIGateway validates each leaf, then reconstructs the upstream
`provider` policy itself from an explicit allowlist and forces `require_parameters=true`.

Approved artifacts: Linear OME-704 (parent OME-479) plus
`.agent-team-AIGW/expose-validated-openrouter-price-and-privacy-routing-controls-per-request/`
(task definition + implementation plan, both reviewed 2026-07-30).

## Planned changes

Unit U1 — provider-owned rules and published contract:

- `src/aigateway/core/chat_parameters/_types.py` — add `pattern` + `max_length` string
  constraints to `ParameterSchema` (construction-time validation; full-match semantics;
  rendered into the published JSON Schema).
- `src/aigateway/plugins/openrouter_provider/parameters.py` — five provider-local schemas +
  five `provider_native_rule` entries; bump `_REVISION`.
- `src/aigateway/core/parameter_projection.py` — reject every top-level key beginning with
  `provider_params.` so the object wrapper is the only caller addressing form.
- `src/aigateway/plugins/openrouter_provider/observations.py` — routing-policy source label +
  the five reviewed static observations at their wrapper request paths.
- `src/aigateway/plugins/openrouter_provider/plugin.py` — include the routing-policy
  observations in `chat_parameter_observations`.

Unit U2 — safe provider reconstruction:

- `src/aigateway/plugins/openrouter_provider/routing_policy.py` (new) — allowlist
  reconstruction of the upstream `provider` object + fixed-point decimal normalization.
- `src/aigateway/plugins/openrouter_provider/dispatch_errors.py` — sanitized non-retryable
  503 `provider_unavailable` for an unexpected projected policy (no raw values as arguments).
- `src/aigateway/plugins/openrouter_provider/plugin.py` — `prepare_chat_body` reconstructs
  instead of assigning the constant.

Units U3/U4 — route/cache/security coverage and documentation.

## Test plan

RED first, per unit:

- Schema: pattern/max_length accept-reject at the boundaries (64 vs 65 chars), invalid regex
  and unanchored pattern rejected at construction, constraint on a non-string type rejected,
  rendered JSON Schema carries `pattern` + `maxLength`.
- Rules: `sort="price"` accepted and any other sort malformed; max-price accepts `"0"` and
  positive fixed-point strings, rejects numeric JSON, negatives, exponents, whitespace and
  non-finite spellings; `data_collection` enum; `zdr` boolean; unknown nested leaves stay
  named `unknown`; every new rule declares `cache_behavior="bypass"`.
- Dotted aliases: top-level `provider_params.*` keys (existing `top_k` and the new paths)
  fail closed rather than acting as a second addressing form.
- Provider boundary: omission still yields exactly `{"require_parameters": true}`; each leaf
  reaches its documented `provider.*` wire location; combined request carries all five plus
  strictness; `zdr=false` omitted, `zdr=true` preserved; decimal normalization is exact and
  never exponential; an unexpected projected key/shape returns exactly HTTP 503
  `provider_unavailable` with no raw value, before cache, credential material or dispatch.
- Route: valid controls dispatch once; invalid values return the stable 400 rejection shape
  with `captured == {}`; raw `provider`/`order`/`only`/`ignore`/`allow_fallbacks`/`route`/
  `models`/`plugins` stay named unknown rejections; `api_base`/`base_url`/`model_list`/
  `extra_body` keep silent pre-credential stripping; no-eligible-endpoint stays sanitized and
  preserves credential state; every new control reports cache bypass via
  `caller_cache_bypass_paths`.
- Contract: `/v1/model-parameters` publishes all five paths with bounded schemas, the
  routing-policy source and `cache_behavior="bypass"`; `/v1/models` summary derives from the
  same rules.

Load-bearing assertions run against final wire JSON through the installed litellm 1.87.0
OpenRouter transformation, not only the captured transport kwargs.

## Acceptance

Definition of done as filed on OME-704 (13 items), plus: existing OpenRouter security,
strict-routing, control-plane-isolation and no-eligible-endpoint suites pass unchanged in
meaning; raw `provider` remains unruled; `require_parameters=true` cannot be relaxed at
either layer; all `apps/aigateway` gates green via `run_gates.py aigateway`.

## Outcome

- **Actual files:**

  New source:

  - `src/aigateway/plugins/openrouter_provider/routing_policy.py` (303) — the single source of
    truth: `PRICE_PATTERN`, `PRICE_MAX_LENGTH`, the four schemas, `normalize_price`,
    `ROUTING_CONTROLS`, `routing_policy_rules()`, `build_provider_policy()`.
  - `src/aigateway/core/chat_parameters/_schema.py` (220) — `ParameterSchema`, its type enums,
    the per-type predicates and `ParameterValidationError`, extracted from `_types.py` so both
    halves stay under the 450-line limit (see deviation g).

  Modified source:

  - `src/aigateway/core/chat_parameters/_schema.py` — `pattern` + `max_length` on
    `ParameterSchema`; anchoring, compilability, positive-length and string-capability all
    enforced at construction; length checked before pattern; rendered as `pattern`/`maxLength`.
    (Landed in `_types.py`, then moved here by the deviation-g split.)
  - `src/aigateway/core/chat_parameters/_types.py` (+3/-144) — `ParameterSchema` and its
    validation vocabulary moved out to `._schema`; imports rewired.
  - `src/aigateway/core/chat_parameters/__init__.py` (+14/-10) — the four moved names now
    re-exported from `._schema`; `__all__` unchanged (27 names, all still resolving).
  - `src/aigateway/core/parameter_projection.py` (+19) — dotted `provider_params.*` top-level
    keys rejected structurally (before rule resolution), mirrored in `_addressed_request_paths`.
  - `src/aigateway/plugins/openrouter_provider/parameters.py` (+10) — splices in
    `routing_policy_rules(...)`.
  - `src/aigateway/plugins/openrouter_provider/observations.py` (+30/-4) — the distinct
    `openrouter:routing-policy` provenance label and the five reviewed observations, derived
    from `ROUTING_CONTROLS`.
  - `src/aigateway/plugins/openrouter_provider/dispatch_errors.py` (+28) —
    `_unexpected_routing_policy_error()`: non-retryable, argument-free, sanitized 503.
  - `src/aigateway/plugins/openrouter_provider/plugin.py` (+20/-28) — `prepare_chat_body`
    reconstructs via `build_provider_policy`; the OME-651 rationale moved to `routing_policy.py`.

  New tests (298 added; all green):

  - `tests/unit/openrouter/test_openrouter_routing_policy.py` (424) — 156 tests: rules,
    schemas, published contract, normalization.
  - `tests/unit/openrouter/test_openrouter_routing_policy_wire.py` (365) — 56 tests: final wire
    JSON through installed litellm 1.87.0, strictness, the 503.
  - `tests/unit/openrouter/test_openrouter_routing_policy_routes.py` (754) — 86 tests: the full
    §4.1 route/security/cache matrix through real `POST /v1/chat/completions`.

  Modified tests: `test_chat_parameter_schema_validation.py` (+106),
  `test_parameter_projection_hardening.py` (+77/-11), `test_caller_cache_policy.py` (+11),
  `test_openrouter_parameter_overlay.py` (+10/-1), `test_openrouter_strict_routing.py` (+29/-10).

  Docs: `docs/openrouter-routing-controls.md` (161, new) + `README.md` (+9, link).

- **Commits:** `837969e5` — `feat(aigateway): validated OpenRouter price and privacy routing
  controls` (`Refs: OME-704`). 21 files, +2859/-208. Pre-commit hooks green (trailing
  whitespace, end-of-file, large files, merge conflicts, ruff check, ruff format).
  **Not pushed** — no upstream, no PR yet; push is a separate authorization.

- **Gates:** `uv run .claude/scripts/run_gates.py aigateway --skip-append-only` → **ALL GATES
  GREEN** (clean serial run): ruff check · ruff format --check (373 files) · pyright (0 errors,
  0 warnings, 0 informations) · `check_no_enterprise.py` (OK) · `pytest --cov=aigateway
  --cov-fail-under=80`. Full suite `pytest -m "not live"` → **2555 passed, 7 skipped, 33
  deselected**. Baseline progression 2412 (pre-U1) → 2468 (U2) → 2554 (U3) → 2555.

  Append-only check skipped deliberately, with all five prior-test modifications adjudicated
  (three additive/strengthening; two approved by the owner this session; one approved earlier) —
  see Deviations c/d/e. No prior test was weakened, deleted or skipped.

  One flake observed and dismissed with evidence:
  `tests/unit/auth/test_login.py::test_unknown_user_timing_close_to_wrong_password` failed once
  while two full pytest processes ran concurrently, then passed 3/3 in isolation. It is a
  comparative wall-clock timing assertion and the diff touches nothing under `auth/`.

- **§5.4 final diff review:** performed against runtime evidence, not inspection alone.
  Verified — no widening of raw `provider`/control-plane access (excluded members are refused,
  not dropped: `order`, `allow_fallbacks`, an unknown `max_price` sub-key each yield the
  sanitized 503); exact agreement among the five rules, the five published schemas and the five
  wire locations, with `"1.500"`→`"1.5"` normalization; `require_parameters` cannot be relaxed
  (`{"require_parameters": false}` in, `{"require_parameters": true}` out; forced even on an
  empty projection); no cache eligibility regression (all five rules `bypass`, matching every
  other OpenRouter rule; `build_cache_key` untouched); no misleading ZDR or budget claim (both
  code comments and the caller doc scope `zdr` to upstream endpoint eligibility and `max_price`
  to unit rates); no provider pinning (`sort` admits only `price`); no new plaintext credential
  or prompt storage (the diff adds no logging and no persistence path).

- **Deviations:**

  a. **Stronger than planned:** `max_length < 1` is a construction error, not just a no-op
     constraint — an unfireable constraint reads as protection that is absent.
  b. **`_REVISION` deliberately NOT bumped** from `"openrouter-2026-07"`. `_rules_revision`
     already folds each rule's `request_path` and schema into the contract digest, so adding
     five rules moves the published id on its own. Bumping would additionally signal that the
     twelve pre-existing projections changed semantics, which they did not.
  c. **A prior `duplicate_channel` assertion moved layers** (owner-approved this session). The
     new structural guard fires before rule resolution, so the classifier can no longer reach
     `duplicate_channel` for a dotted key; the scenario is kept verbatim with the outcome
     updated to `unknown`, and the collision invariant it guarded is now asserted at its own
     layer via `_project` raising `_TargetCollision`.
  d. **Provenance allowlist grew by one reviewed label** (owner-approved this session):
     `openrouter:routing-policy` added in `test_openrouter_parameter_overlay.py`, plus a *new*
     `isdisjoint({"openrouter:models", "openrouter:openapi"})` assertion so the reviewed label
     can never be mistaken for network evidence.
  e. **An OME-651 test retargeted** (approved in the prior session) from "the boundary
     overwrites a caller `provider`" to "the boundary refuses it with a 503" — the behaviour it
     pinned was replaced by a strictly stronger one.
  f. **Documentation landed at a new path.** Plan §5.1 said to update "the AIGateway API
     documentation"; no such document existed (README is operations-only). Created
     `docs/openrouter-routing-controls.md` and linked it from a new README "Chat parameters"
     section. `CHANGELOG.md` deliberately untouched (release-please owns it).
  g. **File size — found in the §5.4 review, RESOLVED in this unit** (owner decision). The 48
     added lines took `_types.py` from 446 to 494, past the ≤450 limit. Fixed by extracting
     `ParameterSchema` and its validation vocabulary into `_schema.py`, following the OME-602
     precedent that already split this same package into `_types` + `_algebra` for this exact
     reason. Result: `__init__.py` 91 · `_algebra.py` 253 · `_schema.py` 220 · `_types.py` 305
     — all four under the limit.

     Safe because the package's `__init__.py` is the sole public surface: nothing in `src/` or
     `tests/` imports a half directly (verified), so the move cannot break an import. Proven
     by all 27 `__all__` names still resolving, `_algebra.py` referencing nothing that moved,
     and the suite unchanged at 2555 passed / 7 skipped. Pure refactor — no test changes, no
     behaviour change; the dependency runs one way, `_types` → `_schema`.

     Not changed: the new 754-line route suite, which is within existing test practice
     (`test_oauth_connections_routes.py` 753, `test_chat_x_profile.py` 1276,
     `test_auth_routes.py` 2049).

- **Not done (explicitly out of merge scope):** the optional authenticated live OpenRouter
  diagnostic (`AIGW_LIVE=1`) verifying one accepted request per control and one
  no-eligible-endpoint combination. Live tests are opt-in diagnostics, never merge gates.
