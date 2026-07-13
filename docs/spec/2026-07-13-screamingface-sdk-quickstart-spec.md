---
title: screamingface — SDK v0.1 quickstart surface (packages/screamingface)
status: approved design — forward spec for the OME-400 slice
created: 2026-07-13
author: Claude (Sonnet 5) + keelan
ticket: OME-400
related:
  - https://linear.app/openmined/issue/OME-400/sf-notebook-ship-00-quickstart-the-sdk-surface-it-needs
  - docs/plan/2026-07-13-screamingface-sdk-quickstart.md
  - docs/spec/2026-07-11-url4-package-v1-spec.md (scaffold + hexagonal precedent)
  - screamingface-brand/product-demos (prototype: screamingface-contract + notebooks — the API contract source)
---

# screamingface SDK — v0.1 quickstart surface

## 1. Purpose & scope

`screamingface` (import `screamingface as sf`, PyPI name `screamingface`, path
`packages/screamingface`) is the Python SDK for composing AI-model fusions, evaluating them
on benchmarks, and reading the gain over the best single model. v0.1 ships EXACTLY the
surface `00_quickstart.ipynb` needs (the notebook is the de-facto spec):

```python
import screamingface as sf
sf.mock_widgets(True)                                   # static widget rendering
sf.setup()                                              # connect providers (panel / headless print)
ids = sf.models.list(max_price=20)                      # discover: provider/model ids
fusion = sf.Fusion("fusion", models=ids[:3],
                   reduce="majority_vote", judge=ids[0])
fusion.url                                              # shareable url4:// recipe string
run = fusion.evaluate("gpqa", first=20, seed=0)
run.score, run.baseline, run.gain                       # the payoff read-out
```

**Origin.** The public API is ported from the `screamingface-contract` prototype
(product-demos), which backs the fake-demo notebook series. v0.1 ports the quickstart
slice only and fixes the prototype's flagged API debts on the way in (its
`API_STRUCTURE.md` §5): `first=`/`seed=` are the only sample-size spellings (no `n`/`full`
back-compat), and `sf.models` is a catalog *service*, not a `Pool` collection.

**Non-goals for v0.1** (owned by sibling tickets): leaderboard/submit (OME-402), live
ipywidgets (OME-407), url4 import/`from_url4` + real `(sources)!intent` grammar (OME-408),
custom scripts (`04_custom_scripts`), stacked fusions, remaining benchmark data files,
real inference.

## 2. Architecture — hexagonal, one port

```
        studio surface (public)                engine (internal)
  sf.models.list/.get   Fusion   Run     →   catalog data · fusion core · evaluate loop
             │                                        │
             └────────── EngineBackend port ──────────┘
                              │
               SimulatedBackend (v0.1 adapter, deterministic)
               <real engine adapter — OME-296, later>
```

- **`EngineBackend`** (Protocol, `engine.py`) is the seam: given (model, question,
  benchmark, seed) it produces an answer with cost/latency/token metadata. v0.1 ships one
  adapter, `SimulatedBackend` — deterministic FNV-hash draws over real benchmark
  questions; a per-question shared-difficulty vs idiosyncratic mixture (`correlation`)
  makes majority-vote lift *emerge from real voting math*, not a hard-coded bonus.
- Core never imports an adapter's transport; the real-engine adapter (OME-296) lands as a
  second implementation without touching the public surface. (Mirrors `url4`'s
  `IOLayer`/`StaticIOLayer`/`HttpIOLayer` split.)

## 3. Public surface (v0.1 `__all__`)

| Area | Names | Behavior |
|---|---|---|
| session | `setup()`, `connect(provider, api_key=None)`, `session`, `in_colab` | Keys resolve Colab Secret → env var; in-memory only, never logged/echoed (masked); connecting flips a `connected` flag — the real-auth seam. Headless `setup()` prints instructions. |
| catalog | `sf.models` (service: `.list(search=, provider=, max_price=, min_ctx=, sort=, desc=)` → `provider/model` id list; `.get(id)` → `Model`), `Model` | Static catalog data ported from the prototype (pricing, ctx, ability). Ids are `owner/provider/model`, owner `local` hidden — the federation seam. |
| composition | `Fusion(name, models=[], reduce=, judge=, prompt=, judge_prompt=, loop=)` | Members resolve from `provider/model` ids; `judge` MUST be a member (validated at construction). `reduce` ∈ {`majority_vote`, `weighted_avg`, `best_of_n`, `merge`}; `loop` = `parallel`. |
| sharing | `fusion.url`, `to_url4` | Flat recipe string `url4://<name>?models=<id>+<id>&reduce=…&loop=…&judge=…` using `provider/model` ids. INTERIM format — real url4 grammar emit/parse is OME-408; `share.py` isolates the codec. |
| evaluation | `fusion.evaluate(benchmark, first=None, seed=0, correlation=0.35)` → `Run` | `first=None` = full set; deterministic subsample per seed. Benchmark by id (`"gpqa"`) or name (`"GPQA Diamond"`); v0.1 bundles `_data/gpqa.json` questions (real questions, offline). |
| results | `Run.score/.baseline/.gain/.seed/.sample_size/.benchmark_name/.cost/.url`, repr | `score` = fusion accuracy %, `baseline` = best single-model accuracy, `gain` = score − baseline (all rounded 0.1). Repr: `Run('name' on 'Bench': score=… gain=… cost=$…)`. |
| widgets | `mock_widgets(on=True)`, panel objects with `.value` | v0.1 renders ONLY static mock HTML (brand tokens: radius-0, hairline borders, IBM Plex Mono, gold `#D88507`); every panel's `.value` is the real object (no dead ends). Live ipywidgets deferred. |
| engine | `EngineBackend`, `SimulatedBackend`, `hash01` | The port + v0.1 adapter (§2). |

## 4. Invariants

- **I1 — determinism:** same (fusion, benchmark, `first`, `seed`) → identical run,
  byte-for-byte. `hash01` (FNV-1a) is the only randomness source; no wall-clock, no `random`.
- **I2 — honest lift:** each model's marginal P(correct) equals its `accuracy()`
  regardless of `correlation`; fusion gain emerges from reduce math over per-model answers.
- **I3 — judge is a member:** setting a judge not in `models` raises `ValueError` at
  construction time.
- **I4 — keys never escape:** API keys live only in the in-process `KeyStore`; never in
  reprs, recipes/urls, logs, or exceptions (masked `…xxxx` at most).
- **I5 — port purity:** core modules import neither a real transport nor widget/IPython
  machinery at import time; `import screamingface` works with no extras installed.
- **I6 — recipe identity:** `fusion.url` round-trips the fusion's composition (models,
  reduce, loop, judge) — the recipe is the identity (parsing lands in OME-408).

## 5. Package facts

Distribution `screamingface` v0.1.0 · `requires-python >= 3.12` · zero runtime deps
(pandas/ipywidgets optional extras later) · hatchling build · uv-managed · ruff
(line-length 100, py312, url4's lint selects) · pyright basic · pytest
(`asyncio_mode="strict"`, DeprecationWarning-as-error for the package) · src layout ·
`tests/` suite · executed `examples/00_quickstart.ipynb` committed with outputs · CI lane
`.github/workflows/screamingface-tests.yml` (path-filtered) · not yet released to PyPI.
