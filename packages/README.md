# packages/ — shared libraries

Convention: a `packages/<name>` is a library consumed by **≥2** components and
is **not** independently deployed. Each package is self-contained (own
toolchain, lockfile, CI lane) like an app, but publishes to a registry (PyPI,
npm) instead of deploying.

Apps must never import another app's internals — shared code moves here.

## Planned residents

- **`url4-python-sdk`** — the url4 grammar/AST/resolver as a standalone SDK,
  publishing to PyPI as `url4` (name already reserved on the OpenMined
  account). Extraction source: the url4 executor plugin under
  `apps/server/src/screamingface/plugins/url4_executor/` at the git tag
  `legacy-monorepo-2026-07-08`.
- A Node SDK is planned as `@openmind/url4` (the unscoped npm `url4` name is
  taken).
