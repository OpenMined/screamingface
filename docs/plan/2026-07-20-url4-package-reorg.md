# Plan — reorganize `src/url4` into subpackages (OME-499)

Spec: `docs/spec/2026-07-20-url4-package-reorg-spec.md`. Ledger:
`docs/work/2026-07-20-OME-499-url4-package-reorg.md`.

## Step 1 — move files, no import rewrites yet

`git mv` per the spec's mapping table (preserves history):

```
src/url4/errors.py        -> src/url4/core/errors.py
src/url4/nodes.py         -> src/url4/core/nodes.py
src/url4/_scan.py         -> src/url4/core/_scan.py
src/url4/_annotations.py  -> src/url4/core/_annotations.py
src/url4/grammar.py       -> src/url4/core/grammar.py
src/url4/parser.py        -> src/url4/core/parser.py
src/url4/render.py        -> src/url4/core/render.py
src/url4/builders.py      -> src/url4/core/builders.py
src/url4/context.py       -> src/url4/core/context.py
src/url4/ensemble.py      -> src/url4/core/ensemble.py
src/url4/subrequest.py    -> src/url4/core/subrequest.py
src/url4/io_layer.py      -> src/url4/io/layer.py
src/url4/io_http.py       -> src/url4/io/http.py
src/url4/io_static.py     -> src/url4/io/static.py
src/url4/client.py        -> src/url4/peer/client.py
src/url4/server.py        -> src/url4/peer/server.py
src/url4/cli.py           -> src/url4/cli/app.py
src/url4/_serve.py        -> src/url4/cli/_serve.py
```

`src/url4/dag/` does not move. Create `src/url4/core/__init__.py`,
`src/url4/io/__init__.py`, `src/url4/peer/__init__.py`,
`src/url4/cli/__init__.py` — near-empty (docstring only, no re-exports;
`dag/__init__.py`'s existing pattern of re-exporting is the exception, not
the rule to copy — core/io/peer/cli have no cross-package consumer that
wants a package-level re-export, only `url4/__init__.py` does).

## Step 2 — rewrite intra-package imports

Every `from url4.X import ...` / `import url4.X` inside `src/url4/**/*.py`
(including `dag/*.py`, which imports `core` and `io` modules) gets rewritten
per the moved path. Reference table (old → new import path):

| old | new |
|---|---|
| `url4.errors` | `url4.core.errors` |
| `url4.nodes` | `url4.core.nodes` |
| `url4._scan` | `url4.core._scan` |
| `url4._annotations` | `url4.core._annotations` |
| `url4.grammar` | `url4.core.grammar` |
| `url4.parser` | `url4.core.parser` |
| `url4.render` | `url4.core.render` |
| `url4.builders` | `url4.core.builders` |
| `url4.context` | `url4.core.context` |
| `url4.ensemble` | `url4.core.ensemble` |
| `url4.subrequest` | `url4.core.subrequest` |
| `url4.io_layer` | `url4.io.layer` |
| `url4.io_http` | `url4.io.http` |
| `url4.io_static` | `url4.io.static` |
| `url4.client` | `url4.peer.client` |
| `url4.server` | `url4.peer.server` |
| `url4.cli` (module, not the console-script name) | `url4.cli.app` |
| `url4._serve` | `url4.cli._serve` |
| `url4.dag`, `url4.dag.*` | unchanged |

Preserve every existing `# isort: skip` / lazy-import comment and *why* it's
there (composition-root lazy imports of `io.http`, the `render.py` →
`core.parser` cycle-avoidance import, the `_serve.py` comment about
`_IDENTITY_NAME_RE` being a deliberate private-name reuse). Do not touch the
reasoning in those comments beyond updating the module path they name.

## Step 3 — `url4/__init__.py`

Update every `from url4.X import ...` to the new paths per the table above.
Re-exported names, `__all__`, and docstrings stay byte-identical otherwise.

## Step 4 — `pyproject.toml`

`[project.scripts] url4 = "url4.cli:main"` → `"url4.cli.app:main"`.

## Step 5 — test suite + examples

`grep -rlE '(from url4\.[a-zA-Z_.]+ import|import url4\.[a-zA-Z_.]+)' tests
examples` gives the exact file list (~24 test files + `examples/utils.py`).
Rewrite each import per the Step 2 table (`url4.dag.*` untouched). Do not
alter test logic or assertions — this is a mechanical import-path sweep.

## Step 6 — verify

```
cd packages/url4
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest --cov=url4 --cov-fail-under=95 -q
uv run url4 --version
uv run url4 eval '"ok"'
```

Test count must match pre-reorg (`git stash`/compare, or run on `main` first
to record the baseline count). Pay particular attention to
`tests/unit/test_import_isolation.py` — it asserts the base `import url4`
path stays httpx/uvicorn-free; confirm it still passes unmodified in intent
(only its own import lines move).

## Delegation

- Steps 1–5 are mechanical (file moves + deterministic import-path rewrite
  from the table above) → `mechanic` tier, single pass, spec = this plan
  file + the reference table.
- Step 6 gate run + fix any straggler import the table missed → back to
  `mechanic`/`implementer` as needed.
- `design-reviewer` pass afterward against this plan + the spec's boundary
  rationale (checks: did the mover invent any new public re-exports, did any
  `__init__.py` gain logic beyond re-exports, does the import direction stay
  acyclic core←io←dag←peer←cli, were any docstring/comment "why" explanations
  silently dropped instead of path-updated).

## Acceptance (mirrors the ledger)

- `uv run pytest` green, same test count as `main`.
- `ruff check` / `ruff format --check` / `pyright` clean.
- `url4 --version` / `url4 eval` work via the new console-script target.
- `import url4` public surface unchanged.
