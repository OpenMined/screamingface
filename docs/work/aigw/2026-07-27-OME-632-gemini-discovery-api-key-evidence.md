---
ticket: OME-632
stack: aigateway
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-632 — Report Gemini's live public schema evidence on the API-key path

## Intent

Gemini's sampling evidence in `/v1/model-parameters` comes from a hand-maintained constant. Google
publishes a machine-readable Discovery document for the public `generativelanguage` API, and
`plugins/gemini_provider/discovery.py::parse_generation_config_params` already parses its
`GenerateContentRequest` / `GenerationConfig` subtree bounded and pure — but it has only test
callers. Nothing fetches the document, so the contract never learns when Google's real schema and
our reviewed list diverge.

This unit declares Gemini's discovery source **for the API-key path only** and routes the document
through the shared runtime landed in OME-627. It is the third and last provider on that runtime.

**Live evidence (public document, fetched 2026-07-27).** 353,863 bytes · 210 schemas · 6,332 JSON
nodes · max depth 11 — inside every transport bound (`max_bytes` 1,000,000, `max_json_nodes`
50,000, `max_json_depth` 16). `schemas.GenerateContentRequest.properties.generationConfig` is
`{"$ref": "GenerationConfig"}`, exactly as the existing parser requires. `GenerationConfig`
declares 25 properties, 16 of them scalar:

| Reviewed native | In the live schema |
|---|---|
| `temperature` `topP` `topK` `maxOutputTokens` `stopSequences` | scalar |
| `frequencyPenalty` `presencePenalty` `seed` `candidateCount` | scalar |

and 7 scalars beyond the reviewed set — `enableAffectiveDialog`, `enableEnhancedCivicAnswers`,
`logprobs`, `mediaResolution`, `responseLogprobs`, `responseMimeType`, `responseModalities`. The
remaining 9 properties are `$ref` or untyped (`thinkingConfig`, `responseSchema`, `responseFormat`,
`speechConfig`, `imageConfig`, `translationConfig`, `audioTranscriptionConfig`,
`responseJsonSchema`, `_responseJsonSchema`) and are never dereferenced.

## The auth fork — and why the port stays narrow

Gemini's two auth modes reach two different upstreams. `api_key` talks to the public
`generativelanguage` API, which publishes this document. `oauth` talks to the Code Assist envelope,
which publishes **no** schema — its only honest evidence is the reviewed `build_generate_content_body`
mapping. Presenting the public document as evidence about Code Assist would be an unsound
inference, which is exactly what the two distinct source labels already exist to prevent.

So the source declaration must be auth-aware. Two shapes were weighed:

1. **Declare unconditionally, discard the snapshot on the OAuth path.** Rejected: it pays a fetch
   the document never uses and publishes a `freshness` window describing evidence that was thrown
   away. A false freshness claim is the exact defect class this workstream exists to remove.
2. **Make the declaration auth-aware.** Chosen. Every other provider hook on this path
   (`chat_parameter_rules`, `chat_parameter_observations`, `chat_parameter_tools`,
   `chat_transport_capabilities`) already takes the resolved auth mode; the two discovery hooks are
   the only outliers, so this restores the port's own convention rather than inventing one.

The `DiscoverablePlugin` **Protocol stays at `(*, model)`**: the runtime never reads the auth mode,
and threading an unread value through a port is coupling. Instead the route — which already
resolves the mode — binds it and hands the runtime a narrowed view. Widening the plugin base with
an OPTIONAL keyword is protocol-compatible in the safe direction, so no existing caller, override
or test double changes.

Consequence for the cache: the identity stays `(source, model, revision)` with no auth component.
A provider whose snapshot content varies by auth mode must express that in the ref itself — a
different `source` or `revision` keys separately. Gemini takes the strongest form: no ref at all on
the OAuth path, so no key is ever formed.

## Reading the schema — closed-world over the property map only

The Discovery document's `properties` map is generated from the service definition and is
exhaustive for the schema, so an absent name is a real negative. But the parser deliberately skips
`$ref` and non-scalar properties, so the SCALAR set is **not** a sound vocabulary — negating
against it would fabricate `unsupported` for `thinkingConfig` and friends. The closed-world claim
is therefore scoped to the declared-property key set, with a distinct third outcome:

| Schema state | Observation |
|---|---|
| Reviewed native declared, scalar | `supported`, source `gemini:discovery` |
| Reviewed native absent from the property map | `unsupported` — the map is exhaustive |
| Reviewed native declared but not scalar | none — the field exists; its shape is outside the reviewed surface |
| Scalar declared, not reviewed | `supported` at `provider_params.<native>` — visible-but-DISABLED |
| Document malformed / not linked to `GenerateContentRequest` | none — labelled-static evidence serves |
| Property map over the node bound | `DiscoveryError`; no fabricated verdicts |
| Served from the stale window | the last-good verdicts, `stale: true` |
| Failure past the stale window | none — labelled-static evidence, `freshness.degraded: true` |

`parse_generation_config_params` returns `()` for BOTH "malformed" and "genuinely empty", which a
closed-world reading cannot tolerate — `()` would negate all nine reviewed natives. So the parser
is split: a new reading returns the declared and scalar sets or `None` for malformed, and the
existing function delegates to it, preserving its behaviour and its tests exactly.

Evidence is **endpoint-scoped**: one document describes the whole `v1beta` surface, so it lands in
`endpoint_observations`, unlike OpenRouter's and Hugging Face's per-model rows.

## Planned changes

- `core/discovery_runtime.py` — `AuthScopedDiscoverablePlugin` (the widened provider port) and
  `auth_scoped()`, the adapter that binds one contract read's auth mode. `DiscoverablePlugin` and
  `DiscoveryRuntime.observe` are unchanged.
- `core/plugin_base.py` — `chat_discovery_source` and `discover_chat_parameter_snapshot` gain an
  OPTIONAL `auth_type`, defaulting to `None`.
- `plugins/openrouter_provider/plugin.py`, `plugins/huggingface_provider/plugin.py` — accept the
  new keyword; both are auth-independent and ignore it.
- `plugins/gemini_provider/discovery.py` — `DISCOVERY_URL`, `ALLOWED_ORIGINS`,
  `DISCOVERY_SOURCE_REVISION`; `GenerationConfigSchema` + `parse_generation_config_schema()`;
  `project_generation_config()`; `parse_discovery_snapshot()`; `discover_gemini_snapshot()`.
- `plugins/gemini_provider/plugin.py` — both discovery hooks, gated by ONE shared
  `(api-key, registered gemini id)` predicate.
- `routes/model_parameters.py` — bind the resolved auth mode before observing.
- New tests under `tests/unit/gemini/` and `tests/unit/core/`.

## Test plan

RED first.

Auth scoping:

- The api-key path declares the Discovery source; the OAuth path declares none and never dials.
- The declaration and the fetch share ONE predicate, so "declared, then NOT ATTEMPTED" is
  unreachable.
- The adapter forwards the bound mode to both hooks and leaves the runtime's port unchanged.
- A plugin that ignores the mode behaves identically through the adapter.

Schema projection:

- A declared scalar reviewed native → `supported`, labelled `gemini:discovery`.
- A reviewed native absent from the property map → `unsupported`.
- A reviewed native declared as a `$ref` → no observation.
- An unreviewed scalar → `supported` on the wrapper path.
- Malformed / unlinked / non-mapping documents → no observations, no raise.
- An oversized property map raises rather than truncating.
- Observations are endpoint-scoped, never per-model.

End to end through the route:

- An api-key read reports live evidence and a real freshness window.
- An OAuth read keeps the Code Assist evidence, its label, and the never-observed window, with the
  transport asserting it was never dialled.
- `gateway.status`, the `/v1/models` summary and the rule projection are identical in both.
- Fresh → expired + outage → stale last-good verdicts; past the stale window → labelled-static
  evidence, `degraded: true`.

## Acceptance

- An API-key contract read reports Gemini's live schema evidence with a real freshness window.
- An OAuth contract read performs no fetch and publishes no fetch-derived window.
- A field the live document does not declare is reported unsupported; a malformed document changes
  nothing.
- `gateway.status`, the summary and dispatch are unchanged for the same rule set.
- No unintended egress from the test suite.
- Full aigateway gate green; no prior test weakened.

## Outcome

Status: **DONE**. Every acceptance item holds.

- **Actual files** — exactly as planned, no additions:
  - `src/aigateway/core/discovery_runtime.py` — `AuthScopedDiscoverablePlugin`, `_AuthScopedView`,
    `auth_scoped()`. `DiscoverablePlugin` and `DiscoveryRuntime.observe` untouched.
  - `src/aigateway/core/plugin_base.py` — optional `auth_type` on both discovery hooks.
  - `src/aigateway/plugins/openrouter_provider/plugin.py`,
    `src/aigateway/plugins/huggingface_provider/plugin.py` — accept and ignore the mode.
  - `src/aigateway/plugins/gemini_provider/discovery.py` — `DISCOVERY_URL`, `ALLOWED_ORIGINS`,
    `DISCOVERY_SOURCE_REVISION`, `GenerationConfigSchema`, `parse_generation_config_schema()`,
    `project_generation_config()`, `parse_discovery_snapshot()`, `discover_gemini_snapshot()`.
  - `src/aigateway/plugins/gemini_provider/plugin.py` — both hooks behind one `_discovers()`.
  - `src/aigateway/routes/model_parameters.py` — binds the resolved mode before observing.
  - `tests/unit/core/test_auth_scoped_discovery.py` (12 tests, new),
    `tests/unit/gemini/test_gemini_schema_evidence.py` (21, new),
    `tests/unit/gemini/test_gemini_discovery_route.py` (9, new).
- **Commits:** one — `f37b89af` `feat(aigateway): report Gemini's live schema evidence on the api-key path`.
- **Gates:** `run_gates.py aigateway --skip-append-only` — ruff check · ruff format · pyright ·
  no-enterprise · pytest with `--cov=aigateway --cov-fail-under=80` — **ALL GREEN**. Two fixes were
  needed to get there: a 101-char line, and a test sentinel typed `object()` that could not satisfy
  the `DiscoveryHttpClient` protocol (replaced with the never-called double, which also asserts the
  binder does not dial while forwarding arguments).
- **Deviations:**
  - *An endpoint-scoped document is cached per model.* Cache identity is `(source, model,
    revision)`, and Gemini's one document describes all of `v1beta`, so the four registered ids can
    each hold an entry for the same bytes — at most 4 of 512 entries, one fetch per id per 900 s
    TTL. Adding an endpoint-scoped key class was rejected as a runtime-wide change for a negligible
    saving; the alternative (declaring a source for only one id) would make the other three report
    static-only, which is worse evidence.
  - *Closed-world is scoped to the declared-property key set, not to the scalar subset.* Negating
    against the scalars would fabricate `unsupported` for every `$ref` field the schema plainly
    declares, so a declared non-scalar yields no observation at all — a third outcome rather than a
    forced yes/no.
  - *`parse_generation_config_params` was split, not changed.* It now delegates to
    `parse_generation_config_schema`; its behaviour and its existing tests are untouched. The split
    exists because `()` conflated "document malformed" with "schema empty", which is harmless for
    positive-only evidence and fatal once absence becomes a negative verdict.
  - *`core/plugin_base.py` is 537 lines, over the 450-line guideline* (522 before this unit; the
    delta is docstring). Pre-existing; splitting the abstract port surface is a separate structural
    change, out of scope here.
  - No prior test was weakened, deleted, skipped or rewritten. The optional-keyword widening is
    protocol-compatible in the safe direction, so no existing call site or double needed an edit.
