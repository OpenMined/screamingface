---
title: SDK rich-display contract — catalog views and object cards
ticket: OME-626
status: approved
date: 2026-07-27
---

# SDK rich-display contract — catalog views and object cards

The `widgets-view` HTML gallery is the *target* look for the ScreamingFace notebook SDK.
Only `ConnectionPanel` (`sf.connect()`) and the evaluation `Progress` tracker are real
widgets today. This spec fixes the public value contract for a display-only addition: rich
notebook rendering of the three core objects and two catalog browsers.

## Honesty constraint (the governing rule)

The engine registry advertises **no price, context-window, or capability/ability-score**
data for models, and **no case count or long description** for benchmarks. Cards therefore
render **only real advertised fields**. Fabricated numbers, placeholder bars, or invented
metrics are forbidden — they would violate the SDK's "simulated but honest" stance. If a
field the mock shows has no backing data, it is simply omitted, not stubbed with fake values.

## Real fields (source of truth)

From `_profile.load_registry()` and the authoring types:

- `ModelRecord`: `id`, `provider`, `supported_tools`, `required_connections`.
- `BenchmarkRecord`: `id`, `title`, `grader` (kind/route), `aggregator` (kind/route),
  `tools`, `max_tool_calls`.
- `Model`: `name`, `model` (route), `prompt`, `params`, `url4`.
- `Fusion`: `name`, `members`, `reducer`, `model_ids`, `url4`.
- `Benchmark`: `id`, `title`, `grader`, `aggregator`, `tools`, `max_tool_calls`.

## Public surface

- `Model._repr_html_()` / `Fusion._repr_html_()` / `Benchmark._repr_html_()` — static
  branded cards. Each also gains a concise text `__repr__()` for terminals. These are pure
  functions of the object's own fields; they perform **no** network call.
- `sf.models.view(*, query=None, tools=()) -> ModelsView` and
  `sf.benchmarks.view(*, query=None, tools=()) -> BenchmarksView` — catalog browsers built
  from the engine registry. Interactive (search/filter) when `ipywidgets` is installed;
  static `_repr_html_` catalog otherwise.

## Value contract

- `ModelsView` / `BenchmarksView` expose `.value` = the tuple/list of ids currently shown
  after filtering — the honest analogue of the mock's `.value` line. `view()` reuses the
  same filter predicate as the existing `models.list()` / `benchmarks.list()`, so for equal
  `query`/`tools` arguments the two return the same ids (invariant).

## Out of scope

- `sf.mt(...)` (referenced by the mock; not added here).
- Any engine, gateway, or URL4 change; no new registry fields.
- Selection/"add to fusion" affordances, sorting, or leaderboard rendering (mock-only).

## Accessibility & brand

Reuse the `.sf-ui` token block from `_display.STYLE` (square, hairline, mono/gold; light/dark
via the existing `@media`/theme selectors). All injected model/benchmark text is HTML-escaped.
