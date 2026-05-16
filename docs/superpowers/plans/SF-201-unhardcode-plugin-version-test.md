# SF-201: Unhardcode plugin version in test_plugins_list_endpoint

> **Trivial single-line behavioral fix; no execution plan needed beyond this note.**

**Goal:** Stop `tests/core/test_plugin_settings.py::test_plugins_list_endpoint` from failing on every release-please PR.

**Asana:** [SF-201](https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214854613057177)

## Context

`screamingface.__version__` is the package version (defined in `apps/server/src/screamingface/__init__.py`). Built-in plugins inherit it via `Plugin.version: str = __version__` in `apps/server/src/screamingface/plugin.py:54`. The `/plugins` admin endpoint returns each plugin's `version` field.

`test_plugins_list_endpoint` asserted that value is literally `"0.1.0"`. Release-please updates `__version__` in `__init__.py` (verified by the diff on #171: `0.1.0` → `0.2.0`), so the test breaks on every release PR. Currently making #171 (server 0.2.0) and #172 (desktop 0.2.0) red.

## Change

Two lines in `apps/server/tests/core/test_plugin_settings.py`:

1. Add `from screamingface import __version__ as sf_version` to the imports.
2. Replace the literal `"0.1.0"` in `test_plugins_list_endpoint` with `sf_version`.

The test still verifies the value is exposed; it no longer pins the value.

## Verification

```bash
cd apps/server
uv run pytest tests/core/test_plugin_settings.py -v  # 10/10 pass
uv run ruff check tests/core/test_plugin_settings.py
uv run ruff format --check tests/core/test_plugin_settings.py
```

After merge, rebase #171 and #172 onto main; both should go green.

## Out of scope

- Other `"version": "0.1.0"` strings in the repo are unrelated — they're the **config schema** version (`AppConfig.version`), not the package version. Leave them.
