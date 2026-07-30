---
ticket: OME-631
stack: aigateway
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-631 — Report Hugging Face tool and structured-output support per backend

## Intent

`/v1/model-parameters` reports identical tool and structured-output evidence for every Hugging
Face model. The plugin's observations are entirely labelled-static (`huggingface:static`) and by
construction cannot vary by model — still less by the `:<backend>` the operator pinned. The public
router catalog publishes `supports_tools` and `supports_structured_output` **per backend**, and
`plugins/huggingface_provider/discovery.py::parse_hf_backend_capabilities` already parses it
bounded and pure — but it has only test callers.

This unit declares Hugging Face's discovery source, routes the router catalog through the shared
runtime landed in OME-627, and projects the observed backend row onto the provider-evidence axis.

**Live evidence (public catalog, fetched 2026-07-27, 128 rows / 283 provider entries).** Two
seeded default models overclaim today:

| Seeded model | row | backend | `supports_tools` | `supports_structured_output` |
|---|---|---|---|---|
| `openai/gpt-oss-120b:cerebras` | yes | yes | true | **false** |
| `Qwen/Qwen3-Coder-480B-A35B-Instruct:novita` | yes | yes | true | true |
| `deepseek-ai/DeepSeek-R1:novita` | yes | yes | true | true |
| `google/gemma-2-2b-it:featherless-ai` | **absent** | — | — | — |
| `meta-llama/Llama-3.1-8B-Instruct:nscale` | yes | yes | **false** | true |

Backend-conditionality is real: of the 48 models exposing more than one backend, 11 have backends
that disagree on `supports_tools`. 64 of 283 provider entries omit the flags entirely, so silence
must stay silence. All 283 entries currently report `status: "live"`, so status is not a
discriminating signal today and this unit does not build on it.

## Scope decision (owner, 2026-07-27)

> Project the same HF snapshot into `parameters.tools`, `parameters.tool_choice`, and
> `tools.function` so the detail contract remains internally consistent. This changes only provider
> evidence; `gateway.status` stays enabled and `/v1/models supported_tools` remains unchanged.
> `response_format` keeps its independent verdict.

So `supports_tools` drives three published cells from ONE observation, and
`supports_structured_output` drives `response_format` separately. The evidence axis moves;
`gateway.status`, the summary and dispatch do not. A rule stays the only thing that enables a
parameter or a tool.

## Catalog reading — backend-conditional, silence preserved

The router catalog keys rows by the bare `<org>/<model>` id; the pinned `:<backend>` is one entry
in that row's `providers[]` array. Unlike the OpenRouter catalog there is NO parameter list, so
parameter evidence beyond these two flags stays labelled-static.

| Catalog state | Observation |
|---|---|
| Backend row present, flag `true` | `supported`, source `huggingface:router` |
| Backend row present, flag `false` | `unsupported`, source `huggingface:router` |
| Flag absent from the backend row | none — the catalog is silent, not negative |
| Model row absent | none — labelled-static evidence serves |
| Pinned backend absent from a present row | none — labelled-static evidence serves |
| Gateway id pins no backend at all | none — the router chooses per request, so no single backend verdict applies |
| Served from the stale window | the last-good verdict, `stale: true` |
| Failure past the stale window | none — labelled-static evidence serves, `freshness.degraded: true` |

The existing `_bool_or_none` already encodes "only a genuine JSON boolean is a verdict"; this unit
reuses it rather than re-deriving the rule.

## Planned changes

- `core/chat_parameters.py` — `overlay_tool_capabilities()`: a pure merge that replaces a
  `ToolCapability`'s `provider_support` while preserving its `gateway_status`, mirroring
  `overlay_observations`.
- `core/chat_parameters.py` — `ProviderDiscoverySnapshot` gains `tool_observations`, keeping tool
  evidence distinct from parameter evidence (§5.1).
- `core/plugin_base.py` — `overlay_discovered_tools()` port with an active default; `snapshot is
  None` returns the labelled-local capabilities unchanged.
- `plugins/huggingface_provider/discovery.py` — `discover_huggingface_snapshot()` async fetch over
  the bounded transport; `HF_ROUTER_REVISION`; capability → observation projection.
- `plugins/huggingface_provider/plugin.py` — `chat_discovery_source()` and
  `discover_chat_parameter_snapshot()`, gated by ONE shared `(upstream, backend)` predicate so a
  declared source can never be followed by NOT ATTEMPTED.
- `routes/model_parameters.py` — pass the snapshot through the tools overlay as well as the
  parameter overlay.
- New tests under `tests/unit/huggingface/` and `tests/unit/core/`.

## Test plan

RED first.

Capability projection:

- `supports_tools: true` → `tools` and `tool_choice` observed `supported` from `huggingface:router`.
- `supports_tools: false` → both observed `unsupported`; `tools.function` agrees.
- `supports_structured_output` drives `response_format` independently of `supports_tools`.
- A flag absent from the backend row produces no observation for its paths.
- Absent row / absent backend / no pinned backend → no observations at all.

Tool-capability algebra:

- The overlay replaces `provider_support` and preserves `gateway_status`.
- A tool type the snapshot is silent about keeps its labelled-local verdict.
- No snapshot returns the capabilities unchanged.

End to end through the route:

- Two HF models with different backend rows produce different evidence while `gateway.status` and
  the `/v1/models` `supported_tools` summary stay identical.
- `parameters.tools`, `parameters.tool_choice` and `tools.function` agree within one document.
- Fresh → expired + outage → stale last-good verdict.
- Past the stale window → labelled-static evidence, `degraded: true`.

## Acceptance

- Two Hugging Face models whose backend rows differ produce different detailed contracts.
- No model advertises provider support for a tool or field its pinned backend reports it lacks.
- The three projected cells never disagree within one document.
- `gateway.status`, the summary and dispatch are unchanged for the same rule set.
- Fresh / stale / degraded each produce the documented contract.
- No unintended egress from the test suite.
- Full aigateway gate green; no prior test weakened.

## Outcome

- **Actual files:**
  - `src/aigateway/core/chat_parameters.py` — `ProviderToolObservation` (a tool-type verdict,
    deliberately without `source`/`stale`: the tools section publishes neither, and the mirrored
    request-path rows already carry the provenance for the same verdict);
    `ProviderDiscoverySnapshot.tool_observations` as a third distinct evidence field;
    `overlay_tool_capabilities()` — replaces `provider_support`, preserves `gateway_status` and
    base order, **restrict-only**.
  - `src/aigateway/core/plugin_base.py` — `overlay_discovered_tools()` port with an ACTIVE
    default; `snapshot is None` returns the reviewed capabilities unchanged. It takes no `stale`
    argument because the tools section has no field to put it in.
  - `src/aigateway/plugins/huggingface_provider/discovery.py` — `ROUTER_SOURCE_REVISION`;
    `project_backend_capabilities()` (one catalog boolean → three published cells, with
    structured output kept independent); `parse_router_capability_snapshot()`;
    `discover_huggingface_snapshot()` over the bounded transport. The pre-existing
    `parse_hf_backend_capabilities` is reused unchanged, so `_bool_or_none` remains the single
    definition of "only a genuine JSON boolean is a verdict".
  - `src/aigateway/plugins/huggingface_provider/settings.py` — `pinned_router_target()`: the ONE
    predicate for "is there a single backend to discover", built on the existing slug validator.
  - `src/aigateway/plugins/huggingface_provider/plugin.py` — `chat_discovery_source()` and
    `discover_chat_parameter_snapshot()`, both gated by that predicate.
  - `src/aigateway/routes/model_parameters.py` — the same snapshot now also reaches the tools
    section; `rules` and `transport` stay computed independently of it.
  - `tests/unit/core/test_tool_capability_overlay.py` (new, 10 tests) — the merge algebra and the
    port, including that the `/v1/models` summary is structurally immune.
  - `tests/unit/huggingface/test_huggingface_backend_evidence.py` (new, 20 tests) — the
    projection, the four silence cases, the shared predicate, and the bounded fetch.
  - `tests/unit/huggingface/test_huggingface_backend_route.py` (new, 7 tests) — the HTTP seam:
    three-cell agreement, unchanged gateway status and summary, per-backend divergence, stale
    window, degraded fallback.
- **Commits:** `1c1eb5b7` — *feat(aigateway): report Hugging Face tool support per backend*
  (`Refs: OME-631, OME-479`). Source + tests only.
- **Gates:** `run_gates.py aigateway --skip-append-only` — ruff check · ruff format --check ·
  pyright · check_no_enterprise · pytest `--cov-fail-under=80`: **all green** (3 attempts; the
  first two were an import-order fix and a pyright `reportCallIssue` on a non-existent settings
  field that pydantic's `extra="ignore"` had silently swallowed at runtime). Suite
  **1805 passed / 40 skipped** (1768 before this unit → the 37 tests added here). Targeted
  coverage: `huggingface_provider/plugin.py` 100 %, `settings.py` 100 %, `discovery.py` 99 %,
  `chat_parameters.py` 98 %, `model_parameters.py` 96 %, `plugin_base.py` 94 %. Every line added
  by this unit is covered; the remaining misses are pre-existing.
- **Deviations:**
  - **The catalog reading is deliberately NOT closed-world**, unlike OME-629's. HF's router rows
    carry no parameter vocabulary at all — only per-backend booleans — so there is nothing that
    could make an omission a sound negative. An implementation note in `parse_router_capability_snapshot`
    warns against "aligning" the two readings.
  - **The tools overlay is restrict-only where the parameter overlay is additive.** A discovered
    request path with no rule becomes a visible DISABLED row because `compose_contract_entries`
    derives that status from the rules; a `ToolCapability` bundles evidence AND policy in one
    record, so admitting an unknown tool type would mean inventing a gateway decision. Anchored
    as an INVARIANT rather than left to be rediscovered.
  - **A gateway id that pins no backend gets no discovery at all.** The router selects a backend
    per request, so no single row describes the next call. Every seeded model pins one, so this
    affects only operator-configured unsuffixed ids — which keep the labelled-static contract.
  - **`contract_id` / `context.revision` now move with the tools section's `provider_support`.**
    Pre-existing composer behaviour (the section is a digest input), and correct: a published
    section changed. Noted because it makes the detail contract's id backend-sensitive.
  - **`chat_parameters.py` (584) and `plugin_base.py` (522) remain over the ≤450 guideline** —
    both were already over before this unit (532 / 494). Splitting core vocabulary modules is a
    structural change to a shared surface and stays out of scope; flagged for a dedicated unit.
  - **No prior test was modified.** The planned reuse of `parse_hf_backend_capabilities` held, so
    its existing parser tests needed no change.
