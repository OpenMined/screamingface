---
ticket: OME-605
stack: screamingface
status: complete
started: 2026-08-01
finished: 2026-08-01
---

# OME-605 — Deepen the ScreamingFace SDK modules

## Intent

Improve dependency direction, locality, test seams, and package navigation without changing the
approved public behavior.

## Test plan

- Preserve Client/AsyncClient behavior through controlled Engine adapters.
- Preserve ConnectionPanel behavior through its public widget/static interfaces.
- Preserve transport behavior through the existing protocol server.
- Run Ruff, formatting, Pyright, coverage, notebook generation, distribution checks, and relevant
  SDK/URL4 Cloud end-to-end tests.

## Outcome

- **Actual files:** introduced `_core`, `_engine`, `_evaluation`, and `_ui` responsibility
  packages; moved concrete authentication, catalog, Benchmark HTTP, transport, evaluation, and
  notebook implementations behind those boundaries; reduced `client.py` to lifetime and public
  API delegation; added constructor injection for HTTP and Run transports; consolidated wire
  primitives; removed the standalone Benchmark catalogue decoder; reduced `BenchmarkInfo` to id,
  revision, and total Case count; made `score` the single higher-is-better result instead of
  duplicating it through primary-metric/direction and baseline/gain fields; and ignored Jupyter
  virtual documents without deleting local files.
- **Gates:** Ruff and Ruff format pass; Pyright reports zero errors; the exact CI suite passes with
  333 tests, 14 skips, and 95.07% coverage; the live URL4 Cloud lifecycle E2E passes; wheel and
  sdist build and pass distribution-content validation; committed generated notebooks exactly
  match the deterministic builder.
- **Deviations:** the working copy of `00_quickstart.ipynb` retains user-added exploratory cells
  and an executed one-Candidate run, so the source checker intentionally reports it stale. It was
  not overwritten; generated notebook checks ignore execution outputs and kernel-session metadata.
