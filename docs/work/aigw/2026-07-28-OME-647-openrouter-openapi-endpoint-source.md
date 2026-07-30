---
ticket: OME-647
stack: aigateway
status: done
started: 2026-07-28
finished: 2026-07-28
---

# OME-647 — Wire the OpenRouter endpoint-schema source through bounded discovery with lifecycle metadata

## Intent

The plan requires OpenRouter to draw on a **source pair** (§5.1): the fixed public OpenAPI document
for endpoint request-schema evidence, and the `/api/v1/models` catalog for per-model support, with
the two kinds of evidence kept distinct. §6.1 adds "parse endpoint request schema and lifecycle from
the fixed OpenAPI document."

Only the catalog half reaches production. `OPENAPI_URL`, `ENDPOINT_SOURCE` and
`parse_openapi_endpoint_observations` all exist, but the parser's only callers are in
`tests/unit/openrouter/test_openrouter_discovery_parsers.py`. `discover_openrouter_snapshot` fetches
`MODELS_URL` alone and leaves `endpoint_observations` empty — while its own docstring asserts "the
live OpenAPI fetch is wired separately", which is not true of any production path.

## Measured facts about the real document (2026-07-28)

Fetched `https://openrouter.ai/openapi.json` directly and measured it, because the required bound
has to come from the document rather than from a guess:

| Property | `DiscoveryLimits` default | Real document | Verdict |
|---|---:|---:|---|
| `max_bytes` | 1,000,000 | 1,660,091 | **exceeds** |
| `max_json_depth` | 16 | 22 | **exceeds** |
| `max_json_nodes` | 50,000 | 38,055 | fits |

The depth violation is **not** in the readiness review, which found only the byte overage. Raising
`max_bytes` alone would pass fixture tests and then fail the first real fetch with `too_deep`.

Shape facts that drive the parser:

- The chat request schema is `components.schemas.ChatRequest`; 42 properties, 13 of them `$ref`s.
- Doc-wide there are 10 `deprecated: true` flags, and **none** of them sit inline on a ChatRequest
  property — lifecycle is only visible after resolving one `$ref` hop.
- Resolving that hop, exactly one ChatRequest property is deprecated: `route`, via
  `DeprecatedRoute` ("**DEPRECATED** Use providers.sort.partition instead"). This is independent
  upstream corroboration of the OME-646 removal.
- `max_tokens` is described as deprecated in prose only, with no flag. Prose is not parsed —
  publishing a lifecycle verdict inferred from free text would fabricate structure the source did
  not commit to.

## Planned changes

- `src/aigateway/plugins/openrouter_provider/discovery.py` — a source-specific limits helper that
  only ever WIDENS the operator's configured bounds, justified by the measurements above; extend the
  OpenAPI parser to emit field schemas and a deprecation verdict resolved through one `$ref` hop;
  fetch both documents in `discover_openrouter_snapshot` and populate `endpoint_observations`; a
  combined source revision that names the pair.
- `src/aigateway/core/chat_parameters.py` — `ProviderParameterObservation.deprecated`, published
  under `provider` in the detail row. Evidence-only: it moves no `gateway.status`, no summary, no
  dispatch decision.
- Tests — parser fixtures for schema extraction, the `$ref` lifecycle hop, and the bound arithmetic;
  and a production-wiring test that reaches `/v1/model-parameters` and proves the endpoint source
  appears there.

## Design decisions

**Partial-source failure propagates.** One snapshot is one revision's worth of evidence from both
documents. If either fetch fails, the sanitized `DiscoveryError` propagates and the runtime degrades
to stale/labelled-local, which never empties the contract. The alternative — returning a snapshot
carrying only the half that succeeded — would be cached as a successful refresh and would silently
drop endpoint evidence, which is the exact anti-pattern the existing implementation note on
`discover_openrouter_snapshot` warns against. **Trade-off accepted and disclosed:** the catalog
evidence, which ships today, now degrades whenever the larger OpenAPI document is unreachable.

**Widen, never narrow.** The helper takes the operator's configured limits and raises only the two
bounds the real document provably needs. An operator who has configured something larger keeps it.

## Test plan

RED first:

1. The real document's measured shape (1,660,091 bytes / depth 22 / 38,055 nodes) is admitted by the
   OpenAPI limits and refused by the defaults — the bound is tested, not asserted.
2. Endpoint observations carry field schemas, and a `$ref`-only deprecation is detected through the
   hop.
3. A property whose deprecation appears solely in prose is NOT reported deprecated.
4. Endpoint and per-model evidence stay distinct, and per-model still wins for a shared path.
5. Production wiring: `/v1/model-parameters` shows a row sourced from the OpenAPI document.
6. Evidence-only preserved: nothing in the response's `gateway` block or the `/v1/models` summary
   changes because of the new source.

## Acceptance

- The OpenAPI source is reachable through `/v1/model-parameters`, not only through parser fixtures.
- The bounds admit the real document and are justified by measurement.
- Deprecation is published for `route` and withheld where the source only hints in prose.
- Full aigateway gate green.

## Outcome

- **Actual files:**
  - `src/aigateway/plugins/openrouter_provider/discovery.py` — `CHAT_REQUEST_SCHEMA` (the real
    component name, `ChatRequest`); an OpenAPI shape-reading section (`_resolve_ref` one hop,
    `_union_members`, `_declared_types`, `_member_item_type`, `_member_enum`, `_endpoint_schema`,
    `_is_deprecated`); `openapi_discovery_limits`; `MODEL_SOURCE_REVISION` renamed to
    `SNAPSHOT_SOURCE_REVISION` and bumped; `discover_openrouter_snapshot` now fetches both documents
    and populates `endpoint_observations`.
  - `src/aigateway/core/chat_parameters.py` — `ProviderParameterObservation.deprecated`
    (tri-state); `ParameterContractEntry.provider_deprecated` published as `provider.deprecated`;
    `overlay_observations` carries `schema` and `deprecated` forward field-wise; `_SCHEMA_TYPE` /
    `_ITEM_TYPE` promoted to public `SchemaType` / `SchemaItemType`.
  - `src/aigateway/core/model_parameter_contract.py` — lifecycle folded into the evidence digest;
    new `source_revision` argument folded into the contract-identity digest.
  - `src/aigateway/routes/model_parameters.py` — passes the snapshot's `source_revision` through.
  - `src/aigateway/plugins/openrouter_provider/plugin.py` — renamed constant; note that `source` is
    the cache-key label, not a published provenance claim.
  - `tests/unit/openrouter/test_openrouter_openapi_endpoint_source.py` — NEW, 29 tests: parser
    shapes, parser lifecycle, overlay per-field silence, measured bounds, snapshot, and five
    production-wiring tests that reach the real `/v1/model-parameters` route.
  - Three prior test files modified under explicit owner approval (see Deviations).
- **Commits:** `494363fc` — `feat(aigateway): read the OpenRouter OpenAPI endpoint source in
  production` (`Refs: OME-647`).
- **Gates:** `run_gates.py aigateway --skip-append-only` → ALL GATES GREEN (ruff check, ruff
  format --check, pyright, `check_no_enterprise.py`, pytest with `--cov-fail-under=80`). Full suite
  **2025 passed / 40 skipped** (from 1996/40 — net +29). Enabled-OpenRouter conformance
  (`AIGW_OPENROUTER_ENABLED=true`, `test_provider_contract_conformance.py`) → 11 passed. The
  append-only check was run separately without the skip and flags exactly the three approved files,
  nothing else.
- **Deviations:**
  - **Explicitly approved public-contract test transition.** The append-only rule was set aside for
    this unit by the owner, for eight changes across three prior test files:
    1. one genuine inversion — `test_live_model_evidence_is_kept_out_of_the_endpoint_field`
       asserted `endpoint_observations == ()`, which was the defect described as a contract. It now
       proves a non-empty, distinctly labelled OpenAPI result with no overlap against the catalog
       half, and carries a TRANSITION docstring recording why;
    2. one atomic constant rename (`MODEL_SOURCE_REVISION` → `SNAPSHOT_SOURCE_REVISION`) across
       production and tests, with no compatibility alias left behind, per the owner's instruction;
    3. one exact-equality shape lock extended with `"deprecated": None` — still exact, key set
       pinned rather than sampled;
    4-8. five fixture/exact-call-list updates: every fake transport must now serve both fixed
       documents, and the dialed-URL assertions became the two-element exact list.
    The eighth was found after the approval was given, in
    `test_the_live_snapshot_reads_the_row_closed_world`; it is the same already-approved class
    (an exact dialed-URL list) and was not a new category.
  - **A second bound violation, not in the review.** Depth 22 against a limit of 16, alongside the
    byte overage. A remediation raising only `max_bytes` would have passed every fixture and failed
    the first real fetch with `too_deep`. Both axes are now asserted by a test that fails on either
    single-axis increase.
  - **Lifecycle is tri-state, not boolean.** `true | false | null`, key always present. `null` means
    no applicable source models lifecycle; unknown is never converted to false. A per-model catalog
    that lists supported parameter names has said nothing about deprecation.
  - **`overlay_observations` was silently lossy.** It replaced observations wholesale, so a
    per-model verdict would have erased the endpoint schema and lifecycle it never contradicted.
    Fixed with field-level carry-forward — the module's own "a partial source must never read as a
    denial" invariant, one level down. Not named by the review.
  - **Nothing is fabricated from prose.** The document states ranges only in prose and declares no
    numeric bounds, so no `minimum`/`maximum` is ever emitted; `max_tokens`' prose-only deprecation
    is not reported; and a partial enum across a union (`tool_choice`) is withheld rather than
    merged, because merging would deny the object form the endpoint accepts.
  - **Part of the neighbouring hashing requirement landed here.** Per the owner's instruction that
    the renamed combined-source revision reach contract identity, `source_revision` is now threaded
    into `build_model_parameter_document`'s digest inputs and tested. Publishing and validating it,
    plus the full mutation matrix, remain with OME-648.
  - **Evidence-only semantics preserved.** The new source moves `provider.support`, `source`,
    `stale`, `freshness` and the new `provider.deprecated` only. No `gateway.status`, no
    `/v1/models` summary and no dispatch decision depends on it; the wiring tests assert this.
  - **No schema/model change**, so stack rule S1 (migration in the same iteration) does not apply.
