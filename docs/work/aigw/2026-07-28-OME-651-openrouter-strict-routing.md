---
ticket: OME-651
stack: aigateway
status: done
started: 2026-07-28
finished: 2026-07-28
---

# OME-651 — Force OpenRouter strict routing at the provider boundary

## Intent

OpenRouter defaults `provider.require_parameters` to **false**, and its routing documentation
states that an endpoint which does not support a supplied parameter may still receive the request
and ignore the unknown field. So the gateway can validate a parameter, publish it as `enabled`,
project it onto the wire — and still return HTTP 200 with that parameter having had no effect.

Per-model evidence cannot close this. One OpenRouter model is served by several underlying
provider endpoints with different parameter support, so a model-level verdict cannot speak for
the endpoint that actually serves the request.

The fix is a gateway-owned strict-routing policy forced at the provider boundary, where the
gateway already owns the dispatch body.

## Verified before starting

Probed against the **installed** litellm `1.87.0`, not assumed:

- **`extra_body` is flattened onto the wire top level.** `OpenrouterConfig.transform_request`
  pops `extra_body` from `optional_params` and does `response.update(extra_body)`. So
  `extra_body.top_k` reaches OpenRouter as a top-level `top_k`.
- **A non-OpenAI top-level kwarg is folded into `extra_body` first.**
  `add_provider_specific_params_to_optional_params` (utils.py) moves any passed param not in
  `openai_params` into `extra_body` for every openai-compatible provider, and that fold runs
  AFTER `OpenrouterConfig.map_openai_params` overwrites `extra_body` — so the fold wins.
- **Both routes therefore produce identical final JSON.** Passing `provider={...}` top-level and
  passing `extra_body={"provider": {...}}` both yield
  `{"model":…, "n":2, "provider":{"require_parameters":true}, "stream":false,
  "temperature":0.5, "top_k":40, "usage":{"include":true}}`.
- **OpenRouter bodies already bypass the request cache unconditionally.** `_IGNORED_FIELDS`
  (`core/request_cache/keys.py:24`) omits `api_base`, which `prepare_chat_body` sets on every
  OpenRouter request, so `build_cache_key` always returns
  `CacheBypass(reason="unsupported_fields")`. Adding a dispatch field cannot regress caching
  here because there is none to regress.
- **The caller-facing `provider` rule is already gone** (the schema-less routing controls were
  removed earlier in this branch), so a caller-sent `provider` is rejected as `unknown` with 400
  before any credential is read — proven by the existing
  `test_native_routing_controls_are_refused` and its pre-dispatch ordering tripwire.

## Design decisions

**Top-level `provider` on the dispatch body, not inside `extra_body`.** The two are equivalent on
the wire, so the choice is about meaning inside the gateway. In this codebase `extra_body` is the
output of parameter projection — the native targets a caller's fields were promoted to
(`provider_params.top_k → extra_body.top_k`). Strict routing is gateway policy, not a projected
caller parameter, so it belongs alongside the other gateway-owned dispatch fields `api_base` and
`extra_headers`. This also keeps the existing exact-equality assertions on `extra_body` meaning
what they say — "this is what projection produced" — instead of quietly also asserting policy.

**Injected in `prepare_chat_body`.** That is the trusted preparation boundary: it runs after
classification/projection and before cache planning, credential injection and dispatch, and it
already performs gateway-owned overrides. It is also directly unit-testable without mocking
dispatch, which makes the "a caller cannot override it" proof a plain function call.

**Assignment, not merge.** The injection overwrites `out["provider"]` unconditionally rather than
merging into whatever is there. Two independent layers then guarantee the policy: the classifier
400s a caller-sent `provider`, and the boundary would overwrite it even if the first layer were
ever loosened.

**A frozen module-level constant, copied per request.** The policy value is a single named
constant so it cannot drift between the injection site and the tests, and each request gets its
own dict so no request can mutate the shared policy for the next one.

## Planned changes

- `src/aigateway/plugins/openrouter_provider/plugin.py` — `_STRICT_ROUTING_PROVIDER` policy
  constant; `prepare_chat_body` injects it unconditionally.
- `tests/unit/openrouter/test_openrouter_strict_routing.py` — NEW.

No schema/model change, so stack rule S1 does not apply.

## Test plan

RED first. The wire-level tests run against the installed litellm transform, not a mock — the
whole point is that a library change must break the build loudly rather than silently drop
strictness.

1. Every prepared body carries `provider.require_parameters=true` — including the bare
   model+messages case with no optional parameters at all.
2. A caller-sent `provider` is refused with 400 `unknown` before dispatch (existing coverage),
   AND the boundary overwrites a `provider` planted directly on its input — the second layer.
3. The policy object is not shared between requests, and mutating one prepared body's `provider`
   cannot affect the next.
4. **Final-transform proof:** a body carrying every projected class at once — standard
   (`temperature`, `max_tokens`, `stop`, `response_format`, `seed`, `n`, penalties, logprobs),
   native (`provider_params.top_k`) and tool (`tools`, `tool_choice`) — produces final OpenRouter
   JSON from the installed transform containing `provider.require_parameters=true` together with
   every one of those parameters.
5. **Fallback:** the caller-facing `models` / `route` fallback controls are refused, so the
   primary route is the only route and strictness cannot be bypassed by a caller-selected model
   list; the strict policy survives on the body that does dispatch.
6. **No eligible endpoint:** both shapes of OpenRouter's refusal — a transport 404 and an embedded
   error inside a nominal HTTP-200 body — surface as an explicit sanitized gateway error with no
   raw provider text, never a 200.
7. **Outside the catalog vocabulary:** `n` (which OpenRouter's `supported_parameters` catalog
   vocabulary does not list) reaches the final JSON together with the strict policy, so the
   outcome is an explicit provider decision rather than a silent discard.

## Acceptance

- Every OpenRouter chat dispatch carries `provider.require_parameters=true`, proven on the final
  wire JSON produced by the installed litellm transform.
- No caller-reachable path removes, overrides or weakens it.
- The no-eligible-endpoint outcome is an explicit sanitized gateway error.
- Full aigateway gate green; no prior test weakened.

## Outcome

- **Actual files (as planned, both):**
  - `src/aigateway/plugins/openrouter_provider/plugin.py` — `_STRICT_ROUTING_PROVIDER`;
    `prepare_chat_body` assigns `out["provider"] = dict(_STRICT_ROUTING_PROVIDER)` after the
    pinned `api_base`. 29 lines added, nothing removed or reshaped.
  - `tests/unit/openrouter/test_openrouter_strict_routing.py` — NEW, 18 tests across five
    groups: the policy on every dispatch (bare request, each projected parameter class,
    composition with the existing hardening, projection output undisturbed); a caller cannot
    remove or override it (classifier refusal, boundary overwrite, per-request copy, real
    route); the installed-litellm final-wire-JSON proof; fallback cannot bypass strictness;
    and the no-eligible-endpoint refusal in both of its shapes.
- **Commits:** `bc582317` — `feat(aigateway): force OpenRouter strict routing at the provider
  boundary` (`Refs: OME-651`).
- **Gates:** `run_gates.py aigateway` → ALL GATES GREEN, run **without** `--skip-append-only`
  (append-only check ✓, ruff check ✓, ruff format --check ✓, pyright ✓,
  `check_no_enterprise.py` ✓, pytest with `--cov-fail-under=80` ✓). Full suite **2074 passed
  / 40 skipped**, up from 2056 — the +18 are exactly this module. Enabled-OpenRouter
  conformance → 11 passed.
- **Zero prior tests changed.** The append-only gate passing unskipped is the proof, not an
  assertion. This was a design outcome rather than luck: see the first deviation.

### Deviations

- **The placement decision was worth more than it looked.** Four prior assertions are exact
  equalities on `body["extra_body"] == {"top_k": 40}`. Injecting into `extra_body` would have
  inverted all four and opened a prior-test approval gate. Top-level placement was chosen on
  the merits — `extra_body` is the projection's output and strict routing is not a projected
  caller parameter — and the two considerations pointed the same way, because those tests
  encode precisely the meaning the other placement would have violated.
- **Verified rather than assumed how the value reaches the wire.** litellm carries a
  non-OpenAI dispatch kwarg to OpenRouter through two chained behaviours it does not promise:
  `add_provider_specific_params_to_optional_params` folds it into `extra_body` (and that fold
  runs after `OpenrouterConfig.map_openai_params` overwrites `extra_body`, so the fold wins),
  then `transform_request` flattens `extra_body` onto the wire top level. Both were confirmed
  against the installed 1.87.0 before any code was written, and the final-JSON tests pin them
  so a library change fails the build instead of silently disabling strictness.
- **A latent cache defect was found and deliberately left alone.** `_IGNORED_FIELDS`
  (`core/request_cache/keys.py:24`) omits `api_base`, which `prepare_chat_body` sets on every
  OpenRouter request, so `build_cache_key` already returns
  `CacheBypass(reason="unsupported_fields")` for **every** OpenRouter request — the provider
  has never participated in the request cache. That is why adding `provider` to the prepared
  body costs nothing here. It is a pre-existing defect unrelated to this ticket and is not
  touched. Note for whoever fixes it: `provider` must NOT simply join `_IGNORED_FIELDS`
  alongside `api_base` — strict routing can change which endpoint serves the request and
  therefore the response, so it is not output-neutral the way transport plumbing is.
- **This is a deliberate availability trade, now live.** A request that previously succeeded
  because OpenRouter silently ignored a parameter will now fail with an explicit provider
  error, and endpoint filtering may select a slower or more expensive endpoint. Both are the
  intended consequence — an explicit failure beats a silent wrong answer — but they are a
  real behavioral change for existing OpenRouter callers, not a pure hardening.
- **The refusal path is covered in both of its shapes.** OpenRouter answers "no eligible
  endpoint" either as a transport 404 or as a top-level `error` object inside a nominal
  HTTP-200 body. The second is the dangerous one: a gateway checking only the HTTP status
  would hand back a "successful" completion with no choices — the silent discard wearing a
  different costume. Both are proven to surface as explicit sanitized errors with the raw
  provider text and any named internal endpoint stripped.
- **`n` is covered without asserting OpenRouter's catalog contents.** The gateway does not
  hold a vocabulary list for `supported_parameters` — the discovery parser reads whatever the
  catalog returns — so the test proves the honest gateway-side behaviour (`n` and the policy
  both reach the wire; the provider decides explicitly) rather than pinning a remote list the
  repository has no authority over.
- **No schema/model change**, so stack rule S1 does not apply.
