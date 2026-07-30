---
ticket: OME-629
stack: aigateway
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-629 — Report OpenRouter parameter support per model from the live catalog

## Intent

`/v1/model-parameters` reports identical provider evidence for every OpenRouter model: the
plugin's observations are entirely its reviewed labelled-local endpoint inventory, which by
construction does not vary by model. OpenRouter publishes a per-model `supported_parameters`
array and the gateway already owns a bounded parser for it — but nothing calls it, so the
contract cannot tell a model that supports `top_logprobs` from one that does not.

This unit declares OpenRouter's discovery source, routes the catalog through the shared
runtime landed in OME-627, and overlays the resulting evidence onto the labelled-local
observations.

**Scope decision (owner, 2026-07-27) — the provider-evidence axis ONLY.** Catalog data may
change `provider.support`, `provider.source`, `provider.stale` and `freshness`. It must not
change `gateway.status`, the `/v1/models` summary, or chat dispatch authorization. A rule
stays the only thing that enables a parameter. Dispatch performs no discovery and reads no
discovery state, so a warm and a cold cache cannot make the same request behave differently.

**Effective enforcement stays open.** Dispatch can still forward a parameter the catalog says
a model lacks; OpenRouter ignores it upstream. Closing that needs a separate architecture
decision — stable reviewed model-specific rules, or an atomic capability epoch shared by
summary, detail and dispatch — and neither is introduced here.

## Catalog reading — closed-world inside a present row

OpenRouter documents `supported_parameters` as the array of supported API parameters for a
model, and the catalog can be filtered by it (`/models?supported_parameters=tools`), which
only works if the array is complete enough for negative filtering. Their routing docs also
confirm the failure mode of sending a parameter a model lacks: *"providers that don't support
all the LLM parameters specified in your request can still receive the request, but will
ignore unknown parameters."*

| Catalog state | Observation |
|---|---|
| Row present, parameter listed | `supported`, source `openrouter:models` |
| Row present, parameter omitted but in the catalog's own vocabulary | `unsupported`, source `openrouter:models` |
| Row present, parameter outside the catalog's vocabulary | none — the source is silent, not negative |
| Model row absent | none — labelled-local evidence serves |
| `supported_parameters` missing or malformed | none — labelled-local evidence serves |
| Served from the stale window | the last-good verdict, `stale: true` |
| Failure past the stale window | none — labelled-local evidence serves, `freshness.degraded: true` |

The **vocabulary** is derived from the fetched document itself: the union of every row's
`supported_parameters`. A name the catalog never mentions anywhere is a name OpenRouter does
not track, so its absence from one row proves nothing. This is what makes closed-world sound
rather than a source of fabricated negatives.

This overturns the open-world anchor in `discovery.py` ("an unlisted field is left unknown,
never marked unsupported") — explicitly approved by the owner, together with its tests.

## Planned changes

- `plugins/openrouter_provider/discovery.py` — closed-world `parse_model_catalog_observations`
  with a document-derived vocabulary; rewritten invariant anchor.
- `plugins/openrouter_provider/plugin.py` — `chat_discovery_source()`; the gateway-id
  validation moves up from the fetch hook so "declared a source, then reported NOT ATTEMPTED"
  is unreachable.
- `core/chat_parameters.py` — pure `overlay_observations()` merge algebra.
- `core/plugin_base.py` — `overlay_discovered_observations()` port with an active default.
- `routes/model_parameters.py` — pass the observed snapshot through the plugin's overlay.
- `tests/conftest.py` — a discovery client that fails loudly instead of dialling out.
- `tests/unit/openrouter/test_openrouter_catalog_evidence.py` (new).
- `tests/unit/core/test_observation_overlay.py` (new).

## Test plan

RED first.

Catalog parsing:

- Two rows with different `supported_parameters` yield different observation sets.
- A listed parameter is `supported`; a vocabulary parameter this row omits is `unsupported`.
- A name no row mentions produces no observation in either direction.
- `top_k` maps to the wrapper request path so its observation lines up with its rule.
- Absent row / non-list `supported_parameters` / non-Mapping document → no observations.
- Gateway-owned fields never become observations.

Overlay algebra:

- Dynamic evidence for a path replaces the labelled-local evidence for that path.
- A path only the labelled-local source knows survives untouched.
- A dynamic path with no rule appears as a DISABLED contract row — evidence adds a row, never
  a rule.
- The stale flag is applied to the overlay, not to the static base.

End to end through the route:

- Two models with different catalog rows produce different `parameters` sections while their
  `gateway.status` values stay identical.
- The `/v1/models` summary for those models is unchanged.
- Fresh → expired + outage → stale last-good verdict with the original observation instant.
- Past the stale window → labelled-local evidence, `degraded: true`, no fabricated support.
- Chat dispatch still holds no reference to any discovery machinery (structural test extends).

## Acceptance

- Two OpenRouter models whose catalog rows differ produce different detailed contracts.
- No model advertises provider support for a parameter its catalog row omits.
- `gateway.status`, the summary and dispatch are unchanged for the same rule set.
- Fresh / stale / degraded each produce the documented contract.
- No unintended egress from the test suite.
- Full aigateway gate green; no prior test weakened beyond the approved anchor rewrite.

## Outcome

- **Actual files:**
  - `src/aigateway/core/chat_parameters.py` — `overlay_observations()`: one verdict per request
    path, dynamic wins, silence preserves the base, `stale` stamped in both directions.
  - `src/aigateway/core/plugin_base.py` — `overlay_discovered_observations()` port with an
    ACTIVE default (endpoint then per-model, so per-model wins); `snapshot is None` returns the
    labelled-local evidence unchanged.
  - `src/aigateway/plugins/openrouter_provider/discovery.py` — closed-world
    `parse_model_catalog_observations` over a document-derived vocabulary
    (`_listed_parameters`, `_catalog_vocabulary`); `_LIVE_REVISION` promoted to the public
    `MODEL_SOURCE_REVISION` and bumped to `openrouter:models:closed-world-2026-07`.
  - `src/aigateway/plugins/openrouter_provider/plugin.py` — `chat_discovery_source()`; the
    gateway-id predicate extracted to `_upstream_model_for_discovery` and shared with the fetch
    hook.
  - `src/aigateway/routes/model_parameters.py` — the observed snapshot reaches the `observations`
    argument only; `rules`, `tools` and `transport` are computed independently of it.
  - `tests/conftest.py` — autouse `_no_discovery_egress` guard on `HttpxDiscoveryClient.get`,
    active only when no transport was injected.
  - `tests/unit/core/test_observation_overlay.py` (new, 10 tests) — the merge algebra and the port.
  - `tests/unit/openrouter/test_openrouter_catalog_evidence.py` (new, 23 tests) — the closed-world
    parser, the declared source, and document composition.
  - `tests/unit/openrouter/test_openrouter_catalog_route.py` (new, 5 tests) — the HTTP seam:
    per-model divergence, identical `gateway.status`, stale window, degraded fallback.
  - `tests/unit/openrouter/test_openrouter_discovery_parsers.py` — comment only (see Deviations).
- **Commits:** `19a7ef68` — *feat(aigateway): report OpenRouter parameter support per model*
  (`Refs: OME-629, OME-479`). Source + tests only.
- **Gates:** `run_gates.py aigateway --skip-append-only` — ruff check · ruff format --check ·
  pyright · check_no_enterprise · pytest `--cov-fail-under=80`: **all green**. Suite
  1768 passed / 40 skipped. Targeted coverage of the touched modules: `plugin.py` 100 %,
  `discovery.py` 99 % (single miss is pre-existing `parse_openapi_endpoint_observations`
  defensive guard), `chat_parameters.py` 98 %, `model_parameters.py` 96 %; every line added by
  this unit is covered.
- **Deviations:**
  - **`plugin.py` is 471 lines, over the ≤450 guideline** (428 before this unit). Splitting the
    provider module is a structural change to a shared surface — `PLUGIN` is a module-level
    singleton the loader and several test modules import — and is out of scope here. Flagged for
    a dedicated unit. (`chat_parameters.py` 532 and `plugin_base.py` 494 were already over before
    this unit.)
  - **One prior test file touched — comment only.** `test_openrouter_discovery_parsers.py:96`
    asserted-and-explained "every observation is … positively supported" as if it were a parser
    invariant; under closed-world that is a property of that fixture alone. No assertion, fixture
    or name was changed; an implementation note now says why it holds, so the note cannot be read as a
    licence to revert the closed-world reading. Covered by the owner's explicit approval to
    rewrite the open-world anchor "and its corresponding tests".
  - **Planned "structural test extends" was unnecessary.** The existing
    `test_chat_dispatch_modules_reference_no_discovery_machinery` already forbids
    `chat_discovery_source` in the chat modules, so the new hook was guarded on arrival.
  - **The two pre-existing parser/snapshot test modules needed no rewrite.** In each fixture the
    target row lists the whole document vocabulary, so closed-world produces the same verdicts.
    The owner's approval to rewrite them went unused.
  - **Effective enforcement remains open** (see Intent): dispatch can still forward a parameter
    the catalog says a model lacks. This unit closes model-specific *reporting* only.
