---
ticket: OME-653
stack: aigateway
status: done
started: 2026-07-28
finished: 2026-07-28
---

# OME-653 — Split the remaining oversized AIGateway source modules

## Intent

Three source modules touched by OME-479 are still above the 450-line limit the plan binds to
touched Python files. `core/chat_parameters.py` (643) was split under OME-602; these are the rest:

| Lines | Module |
|---:|---|
| 575 | `core/plugin_base.py` |
| 510 | `plugins/openrouter_provider/plugin.py` |
| 497 | `plugins/openrouter_provider/discovery.py` |

Behaviour-preserving throughout, one commit per module, separate from every functional commit.

## Verified before starting

- **Nothing introspects the class hierarchy.** No `__mro__`, `__bases__`, `__subclasses__` or
  `mro()` anywhere in `src/` or `tests/` — which is what makes the `plugin_base` change below safe.
- **Imported surfaces are small and known**, so a re-export list can be complete rather than
  hopeful:
  - `plugin_base` — 9 names: `ModelEntry`, `ProviderPluginBase`, `PluginSettings`, `OAuthConfig`,
    `OAuthCodeExchangeRequest`, `CredentialStrategy`, `OAuthStrategy`, `credential_strategy_from`,
    `credential_service_provider_for`.
  - `openrouter_provider.plugin` — `OpenRouterProviderPlugin`, `OpenRouterPluginSettings`,
    `OFFICIAL_API_BASE`, and one PRIVATE name a test reaches for:
    `_top_level_error_is_meaningful`.
  - `openrouter_provider.discovery` — `discover_openrouter_snapshot`,
    `parse_model_catalog_observations`, `parse_openapi_endpoint_observations`,
    `openapi_discovery_limits`, `MODELS_URL`, `OPENAPI_URL`, `MODEL_SOURCE`, `ALLOWED_ORIGINS`,
    `CHAT_REQUEST_SCHEMA`, `SNAPSHOT_SOURCE_REVISION`.

## Design decisions

**`plugin_base` cannot be split without splitting the class — measured, not assumed.**
`ProviderPluginBase` alone is 414 lines. Moving out every value type AND both duck-typed resolvers
still leaves 414 + 42 lines of imports = 456, before any module docstring. So the file-level cut
that worked for `chat_parameters` does not reach here.

The class splits along the seam the file already marks with a section comment: the OME-479
chat-parameter contract hooks versus the pre-existing auth / model-registration / dispatch surface.
Those are two distinct ports, and separating them is the split the plan asks for rather than an
arbitrary line cut.

**The contract half is the SUBCLASS, not a mixin.** `available_auth_modes` reads
`supports_api_key()` and `oauth_config()`, and `chat_transport_capabilities` reads
`supports_chat_streaming()` — all three live in the other half. As a mixin, the contract class
would have to redeclare them, creating a second source of truth for each default. As a subclass it
simply inherits them, and the type checker resolves them with no declaration at all. So
`ProviderPluginCore` holds the auth/dispatch surface and `ProviderPluginBase` extends it with the
contract hooks; `ProviderPluginBase` remains the single name every plugin subclasses.

**The two OpenRouter modules get sibling private modules, not packages.** They already live inside
the `openrouter_provider` package and each has one dominant public symbol, so a package-with-
`__init__` would add a directory level for no benefit. The oversized part of each is a block of
module-level helpers ahead of the main symbol, which moves out cleanly:

- `plugin.py` — the LiteLLM control-field vocabulary, the unsafe-global-state check, the
  control-strip and the error builders (lines 1-289) leave; the plugin class stays.
- `discovery.py` — the two parsers leave (the plan names "provider parsers" explicitly); the
  reviewed labelled-local observations, the source revision, the bounds and the fetch
  orchestration stay.

`plugin.py` re-exports `_top_level_error_is_meaningful` so the test reaching for it keeps working —
moving that import would be a test edit, and the point of this item is that no test changes.

## Planned changes

- `core/plugin_base.py` → package: `__init__.py` (re-exports), `_ports.py` (value types +
  credential port), `_provider.py` (`ProviderPluginCore`), `_contract.py` (`ProviderPluginBase`),
  `_resolvers.py` (the duck-typed resolvers).
- `plugins/openrouter_provider/plugin.py` → plus a sibling module for the dispatch hardening.
- `plugins/openrouter_provider/discovery.py` → plus sibling module(s) for the parsers.

No test changes. No schema/model change, so stack rule S1 does not apply.

## Test plan

No new behaviour, so TDD's RED step does not apply; the verification is the inverse.

1. Full suite green with **zero test files modified** — the append-only gate run without a skip.
2. `pyright` green: every import site still resolves, which is what would break first if a name
   failed to survive a move.
3. Public surface of each module diffed against the previous revision by name, not by inspection.
4. Every resulting file ≤450 lines.
5. Enabled-OpenRouter conformance green after the two OpenRouter splits.

## Acceptance

- All three modules, and every file replacing them, at or below 450 lines.
- Identical public surface for each.
- No test file added, changed or removed.
- Full gate green after each split.

## Outcome

**All three modules split, one commit each, none functional.** Every resulting file is at or below
450 lines, and no touched AIGateway *source* file remains above it.

| Commit | Module | Result |
|---|---|---|
| `40f07d3a` | `core/plugin_base.py` (575) | package — 41 / 97 / 210 / 297 / 69 |
| `cb282a60` | `openrouter_provider/plugin.py` (510) | 382 + `litellm_controls.py` 94 + `dispatch_errors.py` 75 |
| `78a3c846` | `openrouter_provider/discovery.py` (497) | 276 + `openapi_schema.py` 214 + `observations.py` 57 |

`core/chat_parameters.py` (643) was the fourth and shipped separately under OME-602 (`bff0b3de`).

- **`plugin_base` package:** `__init__.py` (re-exports 9 names, `__all__`), `_ports.py` (value types
  + credential port), `_provider.py` (`ProviderPluginCore`), `_contract.py` (`ProviderPluginBase`),
  `_resolvers.py`. `ProviderPluginCore` is deliberately NOT exported — it is a file-size seam, not a
  second port.
- **`openrouter_provider/plugin.py`:** the LiteLLM control-plane hardening and the sanitized gateway
  error builders left as two siblings; the plugin class, the two id helpers and the gateway-owned
  dispatch policy stayed.
- **`openrouter_provider/discovery.py`:** the OpenAPI shape reader left as `openapi_schema.py`; the
  shared observation vocabulary and the three source labels as `observations.py`. `discovery.py`
  re-exports `parse_openapi_endpoint_observations`, so one module is still the import path for both
  parsers.

**Gates:** `run_gates.py aigateway` → ALL GATES GREEN after **each** of the three splits, run
**without** `--skip-append-only` every time (append-only ✓, ruff check ✓, ruff format --check ✓,
pyright ✓, `check_no_enterprise.py` ✓, pytest `--cov-fail-under=80` ✓). Enabled-OpenRouter
conformance after the two OpenRouter splits: 11 passed.

**Behaviour preservation, proved three ways per split rather than asserted:**

1. **Zero test files touched** — the append-only gate passing unskipped is the machine proof, and it
   is the strongest single claim here: a split that needed a test edit would not have been
   behaviour-preserving.
2. **pyright green** — every import site in `src/` and `tests/` still resolves.
3. **Surface diffed by AST against the previous revision**, not eyeballed. `newly exposed: NONE` in
   all three cases. Specifically:
   - `plugin_base` — 9 vs 9 names, `missing: NONE`; class members 36 vs 36, `lost: NONE`,
     `gained: NONE`, nothing defined in both halves, `__abstractmethods__` unchanged.
   - `plugin` — the names that stopped being reachable are three incidental import leaks
     (`HTTPException`, `Mapping`, `NonRetryableProviderError`) and six private symbols with no
     reference outside the package.
   - `discovery` — all twelve externally imported names present; every URL, source label, schema
     name and the snapshot revision string byte-identical; what left is five import leaks and
     thirteen private symbols, `ENDPOINT_SOURCE` among them (asserted in tests only as the literal
     `openrouter:openapi`, whose value did not change).

### Deviations

- **`plugin_base` required splitting the CLASS, not just the file** — measured, not assumed:
  `ProviderPluginBase` alone is 414 lines, and moving out every value type and both resolvers still
  leaves 456 with imports. The contract half became the SUBCLASS rather than a mixin because
  `available_auth_modes` and `chat_transport_capabilities` READ capability declarations in the other
  half; a mixin would have given each of those three defaults two definitions that could drift.
  Verified safe first: nothing in `src/` or `tests/` touches `__mro__`, `__bases__`,
  `__subclasses__` or `mro()`.
- **`plugin.py` produced two siblings, not one.** The planned "dispatch hardening" module would have
  merged two unrelated concerns. Keeping the error builders separate is what stops
  `response_errors.py` — which DETECTS an error inside a provider payload — from acquiring the
  ability to AUTHOR the client-facing one.
- **`discovery.py` kept the catalog parser.** The plan said "the two parsers leave"; moving both
  would have reduced `discovery.py` to a thin fetch shim and still required a third module, because
  `_request_path` / `_observation` / `_dedup_sorted` are shared by both parsers AND by the reviewed
  labelled-local inventory. Only the OpenAPI half left; the shared vocabulary became
  `observations.py`, which also resolves the cycle the alternative would have closed.
- **Source-label constants were regrouped.** `ENDPOINT_SOURCE` moved out of `discovery` with its
  only user, so all three labels now sit together in `observations.py` — which makes the §5.1
  "distinct labels" requirement visible in one place rather than two.
- **`__all__` is load-bearing in the two package splits, not decoration.** Without it a re-exporting
  `__init__` also re-exports whatever the halves imported, quietly widening the public surface while
  every test still passes. `newly exposed: NONE` is the check that catches it.
- **No RED step, deliberately.** There is no new behaviour to drive a failing test; the inverse
  check — the whole suite green with nothing edited — is the stronger claim and is machine-enforced.
- **No schema/model change**, so stack rule S1 does not apply.
- **Eight touched TEST modules remain above 450 lines** and are NOT covered by this item. Splitting
  them means editing prior test files, which the append-only rule makes a Confidence-Gate decision.
  Raised with the owner separately with exact counts; seven of the eight were authored by this
  branch, and `tests/unit/test_chat_x_profile.py` was already 1269 lines before the branch existed.
