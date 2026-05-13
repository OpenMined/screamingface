# DEMO-009 — `python_runner` plugin scaffold + scripts-as-config

- **Asana:** [task 1214568343520691](https://app.asana.com/1/1185126988600652/task/1214568343520691)
- **SF ticket:** SF-156
- **Parent:** [DEMO] Leaderboard Demo — Sergey core track
- **Owner:** A (Sergey)
- **Due:** 2026-05-12 (overdue as of 2026-05-13)
- **Priority:** High
- **Estimate:** 1 day
- **Phase / week:** Phase 1, Week 1
- **Dependencies:** none
- **Branch:** `SF-156-python-runner-scaffold` (off fresh `origin/main`)
- **Confidence:** ~97% after wiring verification (auto-discovery, `add_router` signature, `PluginSettings` import, `sf.json` activation list all confirmed against current code)

## Goal

Land the `python_runner` plugin scaffold that registers the `/python` URL4 backend dispatch path and exposes a `scripts: dict[str, str]` settings field — Python source-as-config, edited via the SF settings UI, persisted in `sf.json`.

No execution logic in this ticket; that arrives in DEMO-010 (subprocess runner), DEMO-012 (sandbox-exec), DEMO-013 (real routes), DEMO-016 (vendored scripts), and DEMO-030 (Monaco RJSF widget).

## Scope

In scope:
- New plugin package `screamingface.plugins.python_runner`.
- Plugin class subclassing the bare `Plugin` (NOT `BackendApiPluginBase`, since `/python` is unauthenticated and local-only — no OAuth/interpreter machinery).
- `PythonRunnerSettings` with the `scripts` dict field annotated `x-code-editor`, name-validated by `^[a-zA-Z_][a-zA-Z0-9_]*$`.
- `_default_scripts.load_vendored_defaults()` reading `_vendored/*.py` at import time, returning `{stem: source}`. Empty dict when the dir is absent.
- Empty `routes.py` stub returning a bare `APIRouter()`.
- Test suite covering plugin load, default-scripts loader, and settings name validation.

Out of scope (explicit):
- Subprocess runner — DEMO-010.
- Sandbox-exec / darwin sandboxing — DEMO-012.
- Real `/python` route + `/data/code/<name>.py` serve route — DEMO-013.
- Vendored HLE Python scripts (`check_correct.py`, `calculate_accuracy.py`) — DEMO-016.
- Monaco code-editor RJSF widget that reads `x-code-editor` — DEMO-030.

## Risks & decisions

1. **Signature drift in spec.** The Asana ticket's code excerpt uses `handle_backend_call(self, intent, sources, app)` positional. The real `Plugin` base contract is `async def handle_backend_call(self, intent: str, *, sources: str = "", app: FastAPI) -> str`. **Decision:** match the real (keyword-only) signature; body remains `raise NotImplementedError("Wired in DEMO-013")`.
2. **`_vendored/` not yet populated.** DEMO-016 lands the vendor files. Ship `_vendored/.gitkeep` so the dir exists; `load_vendored_defaults()` returns `{}` until then — spec explicitly permits this.
3. **Working tree dirty + main behind.** Local `main` is 13 commits behind `origin/main` with uncommitted changes to `apps/server/sf.json` and `claude_backend_api/plugin.py`. Per standing rule, branch from fresh `origin/main`. Stash the dirty changes before branching, restore after the PR opens.
4. **`sf.json` activation list edit IS required.** Discovery (via `pkgutil.iter_modules` in `core/registry.py`) auto-finds the plugin package, but activation reads the explicit `plugins: [...]` list in `apps/server/sf.json`. `"python-runner"` must be appended. The dirty working tree already has `M apps/server/sf.json`; expect a trivial merge on `git stash pop` after the PR — both edits are list appends.
5. **Spec's `setup()` snippet uses wrong API.** Asana ticket shows `routes.register(create_router(app=app))`. Real `RouteRegistry` (verified in `core/routes.py:28`) is `add_router(plugin_name: str, router: APIRouter, *, prefix: str = "")`. **Use:** `routes.add_router(self.name, create_router(app), prefix="")`.

## Reference points in the codebase

- Plugin base class & contract — `apps/server/src/screamingface/plugin.py` (`Plugin`, `PluginSettings`, `backend_call_paths`).
- Structural template (strip OAuth) — `apps/server/src/screamingface/plugins/claude_backend_api/plugin.py`.
- Settings base shape — `apps/server/src/screamingface/plugins/backend_api_base/plugin_base.py` (`BackendApiSettingsBase` is the model to *not* inherit; use the bare `PluginSettings`).
- `x-…` JSON Schema annotation precedent — `apps/server/src/screamingface/plugins/url4_specs/plugin.py` (`x-placeholder`, `x-copy-link`).

## Implementation steps (execution order)

### Step 1 — Pre-flight on screamingface repo
1. `git fetch origin`
2. `git stash push -u -m "pre-SF-156 wip"` (parks the dirty `sf.json` + claude_backend_api/plugin.py edits)
3. `git checkout -b SF-156-python-runner-scaffold origin/main`

### Step 2 — Create plugin package
Directory: `apps/server/src/screamingface/plugins/python_runner/`

Files:
- `__init__.py` — re-exports `PythonRunnerPlugin`.
- `plugin.py`
  - `VALID_SCRIPT_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")`
  - `class PythonRunnerSettings(PluginSettings)`
    - `model_config = SettingsConfigDict(env_prefix="SF_PYTHON_RUNNER__", env_nested_delimiter="__")`
    - `scripts: dict[str, str] = Field(default_factory=load_vendored_defaults, description=..., json_schema_extra={"x-code-editor": {"language": "python"}})`
    - `@field_validator("scripts")` rejecting any key not matching `VALID_SCRIPT_NAME`.
  - `class PythonRunnerPlugin(Plugin)`
    - `name = "python-runner"`
    - `description = "Runs Python scripts referenced by URL4 expressions."`
    - `tags = ["product:python"]`
    - `depends = []`
    - `settings_class = PythonRunnerSettings`
    - `backend_call_paths = ["/python"]`
    - `async def handle_backend_call(self, intent: str, *, sources: str = "", app: FastAPI) -> str: raise NotImplementedError("Wired in DEMO-013")`
    - `def setup(self, app, hooks, classes, routes) -> None:` registers the empty router via `routes.add_router(self.name, create_router(app), prefix="")` (mirrors the `BackendApiPluginBase` setup shape).
- `_default_scripts.py`
  - `VENDOR_ROOT = Path(__file__).resolve().parent / "_vendored"`
  - `def load_vendored_defaults() -> dict[str, str]:` returns `{}` if dir missing, else `{path.stem: path.read_text("utf-8") for path in VENDOR_ROOT.glob("*.py")}`.
- `routes.py` — `def create_router(app) -> APIRouter: return APIRouter()` with a docstring noting "real routes land in DEMO-013".
- `_vendored/.gitkeep` — empty file with a comment hint (in `__init__.py` or top of `_default_scripts.py`) pointing at DEMO-016.

### Step 3 — Tests
Directory: `apps/server/src/screamingface/plugins/python_runner/tests/`

- `__init__.py` — empty.
- `test_plugin_loads.py`
  - `from screamingface.plugins.python_runner.plugin import PythonRunnerPlugin` succeeds.
  - `PythonRunnerPlugin.name == "python-runner"`.
  - `PythonRunnerPlugin.backend_call_paths == ["/python"]`.
  - `PythonRunnerPlugin.settings_class is PythonRunnerSettings`.
  - `"x-code-editor"` appears in the JSON Schema produced by `PythonRunnerSettings.model_json_schema()` under `scripts`.
- `test_default_scripts.py`
  - Empty/absent vendor dir → `load_vendored_defaults() == {}`.
  - Monkeypatch `VENDOR_ROOT` to a `tmp_path` containing `foo.py` and `bar.py` → returns `{"foo": "...", "bar": "..."}`.
- `test_settings_validation.py`
  - Valid names (`foo`, `foo_bar`, `_x1`) — instantiates fine.
  - Invalid (`"foo bar"`, `"123abc"`, `"x-y"`) — raises `ValidationError`.

### Step 4 — Activate plugin in `sf.json`
- Discovery is automatic (`core/registry.py` walks `screamingface.plugins` via `pkgutil.iter_modules`), but activation is gated by the explicit list at `apps/server/sf.json` → `plugins`.
- Append `"python-runner"` to that array. Keep ordering near other backend-api / runtime plugins for readability.
- Boot the server and `curl /plugins` → `python-runner` appears with `backend_call_paths: ["/python"]`.

### Step 5 — Gates (all must be green)
```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/ -v
uv run pyright src/screamingface/plugins/python_runner/
uv run ruff check src/screamingface/plugins/python_runner/
```

### Step 6 — Commit & PR
- Commit: `feat(python-runner): scaffold plugin + scripts-as-config setting (SF-156, DEMO-009)`.
- Push branch; open PR against `main` with body that includes:
  - Link to the Asana task.
  - The acceptance-criteria checklist copied from the ticket, all items ticked.
  - "Out of scope" reminder pointing at DEMO-010/012/013/016/030.
- Do NOT auto-merge — leave for review.
- After PR opens, `git stash pop` to restore the parked wip on `main`.

## Acceptance criteria (mirrors Asana ticket)

- [ ] `from screamingface.plugins.python_runner.plugin import PythonRunnerPlugin` succeeds.
- [ ] `/plugins` listing shows `python-runner` when the SF server starts with the plugin active.
- [ ] `backend_call_paths` contains `/python` (verifiable by introspecting the registry).
- [ ] `PythonRunnerSettings` exposes a `scripts` field with `x-code-editor` annotation in its JSON Schema.
- [ ] On first launch, `settings.scripts` contains the vendored entries (empty dict acceptable until DEMO-016).
- [ ] Invalid script names (`"foo bar"`, `"123abc"`, `"x-y"`) rejected at config load with a clear error.
- [ ] pyright + ruff clean.

## File map (final)
```
apps/server/src/screamingface/plugins/python_runner/
├── __init__.py
├── plugin.py
├── _default_scripts.py
├── routes.py
├── _vendored/.gitkeep                 # populated in DEMO-016
└── tests/
    ├── __init__.py
    ├── test_plugin_loads.py
    ├── test_default_scripts.py
    └── test_settings_validation.py
```
