---
ticket: OME-859
stack: url4-cloud
status: in_progress
started: 2026-08-17
finished:
---

# OME-859 — Populate the declared model world from aigateway's compiled seeds

## Intent

Epic `OME-815` took aigateway's compiled model seeds to 113 ids. `apps/url4-cloud/url4.toml`
declares 25, so 88 models cannot be addressed in a url4 expression and do not appear in
`GET /v1/models`. This unit moves the declared model list out of TOML into a validated Python
registry that mirrors the benchmark registry, and makes CI fail when the registry and the
gateway's compiled seeds disagree in either direction.

The current guard only asserts `declared ⊆ aigateway`, so all 88 additions landed CI-green. The
guard becomes a set equality, which is the property that keeps the two in step.

## Planned changes

Create:

- `apps/url4-cloud/src/url4_cloud/models/__init__.py`
- `apps/url4-cloud/src/url4_cloud/models/registry.py` — `ProviderSeed`, `ModelRegistry`,
  `EMPTY_MODEL_WORLD`
- `apps/url4-cloud/src/url4_cloud/models/builtins.py` — `BUILTIN_MODEL_WORLD`
- `apps/url4-cloud/src/url4_cloud/models/seeds/{anthropic,codex,gemini_cli,antigravity,openrouter,huggingface}.py`
- `apps/url4-cloud/tests/unit/test_model_registry.py`
- `apps/url4-cloud/tests/unit/test_world_config_registry_merge.py`

Modify:

- `apps/url4-cloud/src/url4_cloud/world_config.py` — `load_config(env, *, registry=…)` plus the
  merge; the registry is the base world, TOML layers on top
- `apps/url4-cloud/url4.toml` — remove the 25 `[[aigateway.models]]` stanzas, keep the knobs,
  rewrite the header doctrine (most of it moves to the registry docstring), correct the stale
  HuggingFace footer claim
- `apps/url4-cloud/tests/unit/test_declared_models_match_aigateway.py` — subset assertion becomes
  set equality; add the sixth (HuggingFace) extraction entry
- `apps/url4-cloud/tests/unit/test_executable_model_routes.py`,
  `test_draco_lineup_declared.py`, `test_web_search_routing.py`, `test_runner_config.py` — these
  call `load_config`; adjust for the registry default
- `apps/url4-cloud/README.md`, `apps/url4-cloud/docs/execution-flow-diagrams.md`,
  `apps/url4-cloud/docs/request-workflow.md` — they describe `url4.toml` as *the* declaring surface

Not touched: `apps/aigateway` source. The guard reads its plugin source with `ast`; nothing in
aigateway changes, so this stays a single-app unit rather than a cross-cutting epic.

## Test plan

Batch 1 — `models/registry.py` (RED first):

- a bare slug is canonicalised with its provider prefix
- an already-qualified slug is left untouched (prefixing is idempotent)
- the same id from two seeds raises
- an id with a character outside `ALPHA / DIGIT / - _ . ~` other than `:` raises
- a colon-bearing id lands in `aigateway_only`, never in `routable`, and never raises
- `EMPTY_MODEL_WORLD` is a valid empty registry

Batch 2 — the `world_config` merge:

- registry ids reach `load_config(...).aigateway.models`
- a TOML entry naming an id the registry lacks is kept (additive)
- a TOML entry with `web_search = false` overrides the registry default for that id
- a TOML entry duplicating a registry id yields exactly one `ModelSpec`
- an `aigateway_only` id never enters the world and never appears in `declared_model_ids`
- `default_route` naming a registry-only id validates (the `OME-795` failure mode)
- `default_route` naming an `aigateway_only` id raises `WorldConfigError`
- `registry=EMPTY_MODEL_WORLD` with TOML-only entries still builds a world

Batch 3 — the guard:

- extraction finds a non-empty slug list in all six plugin sources (non-vacuity)
- `registry.all_ids == aigateway_ids` (both directions)
- the partition is a pure function of the id
- `aigateway_only` equals its pinned 29-member enumeration
- migration-only: every previously declared id is still routable

Batch 4 — projection:

- a registry-declared id appears in `GET /v1/models`
- an `aigateway_only` id answers 404 on `GET /v1/model-parameters` without contacting the gateway

## Acceptance

- `registry.all_ids == aigateway_ids` holds; a new aigateway seed fails url4-cloud CI until mirrored
- all 59 route-legal gap ids are addressable and projected
- the 29 `aigateway_only` ids are enumerated in code and pinned
- no previously declared route id changes or disappears
- `run_gates.py url4-cloud` green

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** <sha — message>
- **Gates:** <run_gates.py result line / counts>
- **Deviations:** <anything that differed from the plan, or "none">
