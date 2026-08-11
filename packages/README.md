# packages/ — shared libraries

Convention: a `packages/<name>` is a reusable library and is **not** itself an independently
deployed service. Each package is self-contained (toolchain, lockfile, CI lane) and may publish
to a registry. Deployable integration code belongs under root `apps/` or in its owning repository.

Apps must never import another app's internals — shared code moves here.

Docs: https://docs.screamingface.ai

## Current residents

- **`url4`** — the Python URL4 grammar/parser, builders, DAG executor, I/O layers, `Url4Node`,
  raw ASGI surface, and `url4 serve` / `url4 eval` CLI. Publishes to PyPI as `url4`.
- **`screamingface`** — the Python Fusion and benchmark SDK (`pip install screamingface`). It
  compiles work to URL4 and calls only a configured ScreamingFace URL4 engine; benchmark data
  loading, grading, aggregation, model dispatch, and tools are engine responsibilities.

A Node SDK may be added later under a separately approved package and release contract.
