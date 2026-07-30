---
title: Client rich-display port
ticket: OME-626
status: approved
date: 2026-07-28
---

# OME-626 — Client rich-display port

## Goal

Bring the approved OME-626/OME-641 notebook presentation into the clean v1 Client without
restoring the frozen SDK interface.

## Public interface

```python
models = sf.models.list()
benchmarks = sf.benchmarks.list()

models = client.models.list()
benchmarks = client.benchmarks.list()
```

Each call returns an immutable, ordered, sequence-like catalogue of typed `ModelInfo` or
`BenchmarkInfo` values. The catalogue:

- supports `len()`, iteration, indexing, and equality with the equivalent tuple;
- has a compact terminal `repr`;
- renders an interactive searchable catalogue when Jupyter and `ipywidgets` are available; and
- renders the same records as static escaped HTML otherwise.

There is no separate public `.view()` method. Search is notebook presentation state, not a second
discovery interface.

## Object display

- `Model` renders its real route, provider, instructions, and supported authoring parameters.
- `Fusion` renders its ordered members and synthesis strategy in separate visible sections.
- `Report` remains the post-evaluation inspection surface, including each Candidate Result's exact
  canonical URL4.

The clean Client has no public Plan or authorable `Benchmark`, `Connection`, `Case`, or `Rubric`
values, so their legacy cards are not restored. `BenchmarkInfo` is represented through the
benchmark catalogue.

## Honesty and portability

- Render only fields present in the typed Client values. Never invent price, context-window,
  capability, tool, or score data.
- Escape all Engine- or researcher-controlled text before inserting it into HTML.
- Rich display is optional presentation. The returned values remain ordinary typed Python data;
  terminal scripts and a Tauri sidecar do not depend on HTML or `ipywidgets`.
- The base package does not gain a mandatory notebook dependency.
