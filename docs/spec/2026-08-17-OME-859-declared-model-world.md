# OME-859 — The declared model world, from aigateway's compiled seeds

**Ticket:** [OME-859](https://linear.app/openmined/issue/OME-859/populate-the-declared-model-world-from-aigateways-compiled-seeds)
· **Ledger:** `docs/work/2026-08-17-OME-859-declared-model-world.md`
· **Stack:** url4-cloud · **Date:** 2026-08-17

## 1. Problem

Epic `OME-815` expanded aigateway's compiled model seeds to 113 ids. PR #581 took OpenRouter from
11 to 69 slugs. PR #583 took HuggingFace from 5 to 24 and Anthropic from 5 to 10.
`apps/url4-cloud/url4.toml` declares 25 ids. Therefore 88 models that the gateway serves are:

- not addressable in a url4 expression, because a route path exists only if `url4.toml` declares
  the id; and
- absent from `GET /v1/models`, because the App projects the gateway catalog onto the same
  declared set.

The gap per provider:

| provider | aigateway | declared | gap | route-legal | colon-blocked |
|---|---|---|---|---|---|
| openrouter | 69 | 10 | 59 | 54 | 5 |
| huggingface | 24 | 0 | 24 | 0 | 24 |
| anthropic | 10 | 5 | 5 | 5 | 0 |
| codex | 5 | 5 | 0 | — | — |
| gemini-cli | 4 | 4 | 0 | — | — |
| antigravity | 1 | 1 | 0 | — | — |

The gap grew silently. Nothing in CI reports it.

## 2. Established facts

Verified against `origin/main` on 2026-08-17. None assumed.

- **F1 — the guard is one-directional.**
  `tests/unit/test_declared_models_match_aigateway.py:174` asserts `declared - aigateway_ids == []`.
  No test asserts the opposite direction, so 88 undeclared ids keep CI green.
- **F2 — the guard omits HuggingFace.** `_SLUG_SOURCES` and `_RETURNED_SLUG_SOURCES` name five
  plugin sources. `huggingface_provider/settings.py` is absent, because HuggingFace had no compiled
  list when the guard was written. PR #583 gave it 24 seeds.
- **F3 — 29 of the 88 ids cannot be routes.** url4's path segment charset is
  `ALPHA / DIGIT / "-" / "_" / "." / "~"` (spec §8), mirrored by `world_config._MODEL_ID_RE:59`. A
  `:` is outside it. All 24 HuggingFace ids carry a `:<provider>` backend pin. Five OpenRouter ids
  carry `:batch` or `:free`. This is a grammar limit, not a policy choice. `OME-819` tracks it.
- **F4 — one file feeds both halves.** The Runner reads `url4.toml` through
  `world_config.load_config` (`runner/main.py:28`). The App reads the same file through
  `world_config.declared_model_ids` (`catalog/__init__.py:97`). This is what makes discovery and
  execution agree.
- **F5 — `benchmarks/` is a shared-leaf precedent.** `.claude/scripts/check_layering.py` names
  `benchmarks` in neither `CONTROL_PLANE` nor `RUN_MODE`, so both halves may import it.
  `runner/main.py:23` and `app.py:21` both import `BUILTIN_BENCHMARKS`. A `models/` package sits in
  the same slot. The layering gate needs no change.
- **F6 — the canonical id rule has no per-provider exemption.**
  `aigateway.core.model_capabilities.canonical_model_id` prefixes a slug with
  `<custom_llm_provider>/` unless the slug already carries that prefix. `OME-795` was caused by a
  hand-written per-provider prefix table that guessed `""` for Anthropic.
- **F7 — two seed lists are env-overridable.** `AIGW_OPENROUTER_DEFAULT_MODELS` and
  `AIGW_HUGGINGFACE_DEFAULT_MODELS` replace their lists at deploy time. Ollama discovers its models
  at run time and has no compiled list.
- **F8 — a `url4.toml` footer claim is stale.** It says ollama and HuggingFace "build their model
  lists at runtime … so they are undeclarable here by construction". That is now false for
  HuggingFace. The conclusion holds only because of F3.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | The declared list is **exhaustive** over aigateway's compiled seeds. No deny-list. | Owner call, 2026-08-17. Every route-legal id the gateway serves becomes addressable. Curation at model granularity was rejected as a surface that drifts by construction. |
| D2 | The list lives in a **Python registry inside url4-cloud**, not in TOML, not generated, not derived at run time. | Owner call. It mirrors `BUILTIN_BENCHMARKS`, gains pyright coverage that TOML cannot have, and lets the colon partition be one expression instead of 29 omissions. |
| D3 | Colon-bearing ids are **partitioned into `aigateway_only`**, listed in the seeds, pinned by a test. Not raised, not escaped, not aliased. | Owner call. Escaping would violate the stated invariant *a route path is exactly `/` + the gateway id. No renaming, no aliases.* Widening the grammar is a separate unit against `packages/url4`. |
| D4 | Seeds are **hand-authored**. No standing generator. | The bidirectional guard (D6) derives truth from aigateway's source, so codegen and hand-authoring have identical correctness guarantees. Codegen would add a build step, a staleness failure mode and rubber-stamped diffs. aigateway's own seeds are hand-authored with a pin test, so this matches the house pattern on both sides of the boundary. |
| D5 | `url4.toml` keeps its knobs. `[[aigateway.models]]` becomes **optional and additive**. It may add an id or set `web_search = false`. It may not remove an id. | F7 leaves real users: ollama deployments and deployments that override the two env vars. Removal has no meaning under D1. |
| D6 | The guard asserts **set equality**, not subset. | F1 is the reason the gap grew unseen. Equality fails on a typo (declared but not served) and on a missed seed PR (served but not declared). |
| D7 | Run-time derivation from `GET /v1/models` is **rejected**. | Route existence would depend on a network call and would differ per caller, because catalogs are per credential. That breaks F4's guarantee and makes `default_route` validation non-deterministic. |

## 4. Design

### 4.1 The `models/` package

```
url4_cloud/models/
  registry.py    ProviderSeed · ModelRegistry · EMPTY_MODEL_WORLD
  builtins.py    BUILTIN_MODEL_WORLD — the one composition root
  seeds/         anthropic · codex · gemini_cli · antigravity · openrouter · huggingface
```

The structure is parallel to `benchmarks/`:

| benchmarks | models | role |
|---|---|---|
| `draco/definition.py` | `seeds/openrouter.py` | one concrete declaration |
| `builtins.py::BUILTIN_BENCHMARKS` | `builtins.py::BUILTIN_MODEL_WORLD` | what this deployment installs |
| `BenchmarkRegistry.install()` | `ModelRegistry.__init__` | validate before the first paid request |

A seed declares **slugs**, not ids:

```python
OPENROUTER = ProviderSeed(provider="openrouter", slugs=("openai/gpt-5.5", ...))
```

The registry applies the F6 rule to produce the id. Two properties follow. Each seed file stays a
byte-comparable mirror of the plugin list it tracks. The prefixing rule exists in one place, which
is what `OME-795` needed.

### 4.2 `ModelRegistry` is the fail-fast boundary

`__init__` performs all validation:

- The same id from two seeds raises `ValueError`, as `BenchmarkRegistry` does for a duplicate
  benchmark id.
- An id with a character outside the F3 charset, other than `:`, raises.
- An id containing `:` is placed in `aigateway_only` and never raises.

It exposes three sets: `routable`, `aigateway_only`, and `all_ids` (their union).

### 4.3 One merge point

```python
def load_config(env, *, registry: ModelRegistry = BUILTIN_MODEL_WORLD) -> WorldConfig
```

Both halves already call `load_config` (F4), so the merge lands inside the single parser they
share and no new call site is created. `declared_model_ids` and `routes_for` see the merged world
without change. The registry supplies the base world. `[[aigateway.models]]` layers on top under
D5: an unknown id is added, a `web_search` value overrides the registry default for that id, and a
duplicate id yields exactly one `ModelSpec`. Ids in `aigateway_only` never enter the world.

### 4.4 The guard

`test_declared_models_match_aigateway.py` keeps its `ast` extraction. aigateway is a separate uv
project and is not installed in url4-cloud's environment, so reading its source stays the honest
method. Four changes:

1. Add the sixth extraction entry for `huggingface_provider/settings.py` (F2).
2. Replace the subset assertion with `registry.all_ids == aigateway_ids` (D6).
3. Pin `aigateway_only` to its exact 29 ids. This is derivable from 2, and it is kept for two
   reasons. It renders the `OME-819` work list as reviewable text. It is the only assertion that
   fails if somebody moves an id from `aigateway_only` to `routable` by escaping or aliasing it,
   which D3 forbids.
4. Assert non-vacuity across all six lists, so an upstream rename cannot empty the reference set
   and turn the guard green when it should fail.

**Scope limit.** Exhaustiveness under D1 is over the **compiled** seeds. F7's env overrides and
ollama's run-time discovery are outside it by construction. The spec states this because
"exhaustive" could otherwise be read as a run-time guarantee.

## 5. Error handling

- A malformed seed fails at import, before the App or the Runner starts. This matches
  `BenchmarkRegistry`, which validates every protocol before the first paid request.
- An unusable `url4.toml` keeps its present behaviour. The Runner fails fast at Job start. The App
  degrades: it logs an ERROR and answers 503 on both catalog routes, rather than taking down run
  submission, streaming and health. `catalog/__init__.py:84-92` states this reasoning.
- `default_route` naming an id no longer in the world raises `WorldConfigError` at load. A
  `default_route` naming an `aigateway_only` id raises for the same reason: it can never resolve.

## 6. Consequences

1. **The error boundary moves outward.** Today an undeclared model fails at url4-cloud as an
   unknown route. After this change all 84 route-legal ids resolve, so a model whose provider is
   disabled or has no credential fails deeper — at the gateway, inside the user's expression, as
   `profile_not_found` or a 400. This is the documented *a declared route is not an enabled
   deployment* caveat applied to 3.4 times more models. Local mode inherits it. The consequence is
   inherent to D1 and is accepted.
2. `GET /v1/models` grows about 3.4 times per caller. The cache is keyed per credential, so the
   entry count does not change. Response and ETag size grow.
3. Benchmark identity must not move. The DRACO judge `openrouter/google/gemini-3.1-pro-preview` and
   the HealthBench judge `openrouter/openai/gpt-5.4` are pinned and affect scores. A
   migration-only assertion, `old_declared ⊆ new_routable`, guards every previously declared id.

## 7. Test plan

Four batches, RED first in each. The full enumeration is in the ledger. The assertions that
protect the invariants:

- `registry.all_ids == aigateway_ids` — the property F1 lacked.
- `aigateway_only` equals its 29-member pin — D3, and the alias guard.
- `default_route` on a registry-only id validates — the `OME-795` failure mode.
- `default_route` on an `aigateway_only` id raises.
- Every previously declared id is still routable — consequence 3.
- An `aigateway_only` id answers 404 on `/v1/model-parameters` without contacting the gateway.

## 8. Out of scope

- Widening url4's segment charset to permit `:`. That is a grammar and conformance change against
  `packages/url4`, tracked as `OME-819`. This design leaves 29 ids blocked and makes the blocked
  set explicit, so unblocking them later is the deletion of one predicate.
- Ollama, and any deployment that replaces a seed list through F7's env vars.
- Any change to `apps/aigateway`. Its plugin source is read by a test and is not modified.
