# SF-159 / DEMO-013 — Wire `/python` backend + `/data/code/{name}.py` serve route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Asana:** [task 1214568425333839](https://app.asana.com/1/1185126988600652/task/1214568425333839)
- **SF ticket:** SF-159
- **Parent:** [DEMO] Leaderboard Demo — Sergey core track
- **Owner:** A (Sergey)
- **Due:** 2026-05-18
- **Priority:** High
- **Estimate:** 1 day
- **Phase / week:** Phase 1, Week 1
- **Dependencies:** DEMO-009 (scaffold), DEMO-010 (`run_script_source`), DEMO-012 / SF-158 (sandboxing) — all landed; this branch is off `SF-158-subprocess-sandboxing` so the sandbox wrapping is active in tests.
- **Branch:** `SF-159-python-backend-and-serve-route` (off `SF-158-subprocess-sandboxing`)

**Goal:** Make `python-runner` actually execute. Add the `GET /data/code/{name}.py` route that serves source from `python-runner.scripts.<name>` settings, and implement `handle_backend_call` on the plugin so a URL4 backend dispatch to `/python` fetches a Python source URL, runs it through DEMO-010's `run_script_source` (which is now sandboxed by SF-158), and returns the JSON output.

**Architecture:** Two changes to the existing scaffold —
1. `routes.py` grows a `GET /data/code/{name}.py` endpoint that reads from the plugin instance's `settings.scripts` dict (via `app.state.plugins.active_plugins["python-runner"].settings`) and returns `PlainTextResponse(..., media_type="text/x-python")`. 404 when the name isn't in settings.
2. `plugin.py::handle_backend_call` switches from `raise NotImplementedError` to: fetch `sources` via the existing `url4_resolve._fetch_url` / `_fetch_relative` helpers, parse `intent` as JSON (empty → `{}`), call `run_script_source(source, payload)`, JSON-encode the result. Wrap the body in a tracing span (`python.handle_backend_call`) and tag failures with `python.source_url` / `python.exit_code` / `python.duration_ms`. Fetch / runner errors translate to `HTTPException(400|500)` with `{kind, message, stderr}` detail.

**Tech Stack:** FastAPI, Pydantic settings, asyncio subprocess (via `run_script_source`), httpx (via `_fetch_url` / `_fetch_relative`), pytest + ASGI transport for in-process E2E.

---

## Spec clarifications (call out before implementation)

The Asana ticket's "after this PR" example URL4 — `(a=1, b=2)!/data/code/check_correct.py` — does **not** match the actual URL4 grammar. `Url4BackendCall` has shape `[name:weight:]path(context)!intent` (per `url4_grammar.py:160-184`), with `path` matched against `plugin.backend_call_paths`. The plugin's `backend_call_paths = ["/python"]` is unchanged, so the URL4 form that actually dispatches here is:

```
/python(/data/code/check_correct.py)!{"a":1,"b":2}
```

i.e. `path = /python`, `packed_context = "/data/code/check_correct.py"` (the source URL), `intent = {"a":1,"b":2}` (the JSON payload on stdin). This matches the spec's literal `handle_backend_call(intent="{}", sources="/data/code/check_correct.py", app=...)` example. The Asana ticket prose is wrong about the URL4 surface form; the implementation contract is unambiguous and that's what we build.

The plugin spec uses `get_plugin_settings(app, "python-runner")` — that helper does **not** exist in `screamingface.core.helpers`. The real accessor pattern (per `core/admin_router.py:160-165`) is:

```python
from screamingface.core.helpers import get_plugins_registry
settings = get_plugins_registry(app).active_plugins["python-runner"].settings
```

We'll define a small local helper `_get_python_runner_settings(app)` inside `routes.py` rather than touch shared `core/helpers.py`.

DEMO-016 (vendored scripts) is **not** a dependency: tests inject the script source via settings monkeypatching, not vendored files.

## File structure

- **Modify** `apps/server/src/screamingface/plugins/python_runner/routes.py` — replace stub with `create_router` returning a router with `GET /data/code/{name}.py`.
- **Modify** `apps/server/src/screamingface/plugins/python_runner/plugin.py` — implement `handle_backend_call`; tracing span; error mapping.
- **Create** `apps/server/src/screamingface/plugins/python_runner/tests/test_routes.py` — serve-route tests (200, 404 for missing, name-pattern boundary, post-edit-reload).
- **Create** `apps/server/src/screamingface/plugins/python_runner/tests/test_e2e.py` — in-process E2E: `POST /ensemble` with a URL4 dispatching to `/python(/data/code/<name>.py)!{json}`.
- **Modify** `apps/server/src/screamingface/plugins/python_runner/tests/test_plugin_loads.py` (only if needed) — ensure the existing "plugin still loads" test still passes after `handle_backend_call` changes shape.

The sandbox subpackage from SF-158 is left alone; we rely on it transparently via `run_script_source`.

---

## Pre-flight

- [ ] **Step 0.1: Confirm branch is off SF-158**

```bash
cd /Users/sergey/work/openmind/screamingface
git rev-parse --abbrev-ref HEAD
git log --oneline -3
```

Expected: branch `SF-159-python-backend-and-serve-route`; top 3 commits include the SF-158 sandbox commits (`e6a5fe0`, `6240aaa`, `deb9751`, ...).

- [ ] **Step 0.2: Baseline runner + sandbox tests pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests -v
```

Expected: 43 passed.

- [ ] **Step 0.3: Note the URL4-executor backend-dispatch path**

Open `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py:120-135` and confirm `_dispatch_backend_call` calls `plugin.handle_backend_call(intent_text, sources=sources_text, app=app)` with `sources_text = node.packed_context or ""`. The body we write must match this keyword-style call site.

---

## Task 1: `GET /data/code/{name}.py` serve route (TDD)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/python_runner/routes.py`
- Create: `apps/server/src/screamingface/plugins/python_runner/tests/test_routes.py`

- [ ] **Step 1.1: Write failing tests for the serve route**

Create `apps/server/src/screamingface/plugins/python_runner/tests/test_routes.py`:

```python
"""Tests for the /data/code/{name}.py serve route (SF-159 / DEMO-013)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from screamingface.plugins.python_runner.plugin import (
    PythonRunnerPlugin,
    PythonRunnerSettings,
)
from screamingface.plugins.python_runner.routes import create_router


SCRIPT_BODY = "import json, sys; print(json.dumps({'ok': True}))\n"


@pytest.fixture
def app_with_runner() -> Iterator[FastAPI]:
    """A FastAPI app with python-runner mounted and one script in settings."""
    app = FastAPI()
    plugin = PythonRunnerPlugin()
    plugin.settings = PythonRunnerSettings(scripts={"check_correct": SCRIPT_BODY})

    class _Registry:
        active_plugins = {"python-runner": plugin}

    app.state.plugins = _Registry()
    app.include_router(create_router(app))
    yield app


@pytest.mark.asyncio
async def test_serve_known_script_returns_python_source(app_with_runner: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_with_runner)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/data/code/check_correct.py")
    assert resp.status_code == 200
    assert resp.text == SCRIPT_BODY
    assert resp.headers["content-type"].startswith("text/x-python")


@pytest.mark.asyncio
async def test_serve_unknown_script_returns_404(app_with_runner: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_with_runner)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/data/code/nonexistent.py")
    assert resp.status_code == 404
    assert "nonexistent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_serve_invalid_name_with_dashes_returns_404(
    app_with_runner: FastAPI,
) -> None:
    # has-dashes is not in settings (and could never be — DEMO-009 validator
    # rejects names not matching ^[a-zA-Z_][a-zA-Z0-9_]*$).
    transport = httpx.ASGITransport(app=app_with_runner)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/data/code/has-dashes.py")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_serve_reflects_settings_edit(app_with_runner: FastAPI) -> None:
    plugin = app_with_runner.state.plugins.active_plugins["python-runner"]
    plugin.settings = PythonRunnerSettings(scripts={"check_correct": "print('updated')\n"})

    transport = httpx.ASGITransport(app=app_with_runner)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/data/code/check_correct.py")
    assert resp.status_code == 200
    assert resp.text == "print('updated')\n"
```

- [ ] **Step 1.2: Run tests, expect failures (no real route)**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_routes.py -v
```

Expected: 4 failures — `404` from FastAPI for an unmounted path, since `create_router` currently returns an empty `APIRouter()`.

- [ ] **Step 1.3: Implement the route**

Overwrite `apps/server/src/screamingface/plugins/python_runner/routes.py`:

```python
"""Routes for the python-runner plugin.

Exposes ``GET /data/code/{name}.py`` — the local source-of-truth surface
URL4 expressions reference. Source comes from
``python-runner.scripts.<name>`` settings (DEMO-009); the script-name
validator in :class:`PythonRunnerSettings` already enforces the
``^[a-zA-Z_][a-zA-Z0-9_]*$`` pattern at write-time, so this route only
needs to look the name up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.plugins.python_runner.plugin import PythonRunnerSettings


def _get_python_runner_settings(app: FastAPI) -> PythonRunnerSettings:
    plugin = app.state.plugins.active_plugins["python-runner"]
    return plugin.settings


def create_router(app: FastAPI) -> APIRouter:
    del app  # we read settings off request.app at request time, not bind time
    router = APIRouter(tags=["python-runner"])

    @router.get("/data/code/{name}.py", response_class=PlainTextResponse)
    async def serve_script(name: str, request: Request) -> PlainTextResponse:
        settings = _get_python_runner_settings(request.app)
        if name not in settings.scripts:
            raise HTTPException(
                status_code=404, detail=f"No script named {name!r}"
            )
        return PlainTextResponse(
            settings.scripts[name],
            media_type="text/x-python",
        )

    return router
```

- [ ] **Step 1.4: Run the tests, expect pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_routes.py -v
```

Expected: 4 passed.

- [ ] **Step 1.5: Run the full python_runner suite to confirm no regressions**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests -v
```

Expected: 47 passed (43 baseline + 4 new).

- [ ] **Step 1.6: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/python_runner/routes.py \
        apps/server/src/screamingface/plugins/python_runner/tests/test_routes.py
git commit -m "feat(python-runner): serve scripts at /data/code/{name}.py (SF-159)"
```

---

## Task 2: `handle_backend_call` implementation (TDD)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/python_runner/plugin.py`
- Modify: `apps/server/src/screamingface/plugins/python_runner/tests/test_plugin_loads.py` (only if existing assertions break)

- [ ] **Step 2.1: Write failing unit tests for `handle_backend_call`**

Append a new test module `apps/server/src/screamingface/plugins/python_runner/tests/test_plugin_dispatch.py`:

```python
"""Tests for PythonRunnerPlugin.handle_backend_call (SF-159 / DEMO-013)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from screamingface.plugins.python_runner.plugin import (
    PythonRunnerPlugin,
    PythonRunnerSettings,
)
from screamingface.plugins.python_runner.routes import create_router


ECHO_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({"got": data}))
"""

SYNTAX_ERROR_SCRIPT = "this is not valid python(\n"


def _make_app(scripts: dict[str, str]) -> FastAPI:
    app = FastAPI()
    plugin = PythonRunnerPlugin()
    plugin.settings = PythonRunnerSettings(scripts=scripts)

    class _Registry:
        active_plugins = {"python-runner": plugin}

    app.state.plugins = _Registry()
    app.include_router(create_router(app))
    return app


@pytest.mark.asyncio
async def test_handle_backend_call_relative_source_runs_and_returns_json() -> None:
    app = _make_app({"echo": ECHO_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    result = await plugin.handle_backend_call(
        json.dumps({"a": 1}),
        sources="/data/code/echo.py",
        app=app,
    )

    assert json.loads(result) == {"got": {"a": 1}}


@pytest.mark.asyncio
async def test_handle_backend_call_empty_intent_passes_empty_dict() -> None:
    app = _make_app({"echo": ECHO_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    result = await plugin.handle_backend_call(
        "",
        sources="/data/code/echo.py",
        app=app,
    )

    assert json.loads(result) == {"got": {}}


@pytest.mark.asyncio
async def test_handle_backend_call_http_source_fetched_via_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_app({})
    plugin = app.state.plugins.active_plugins["python-runner"]

    async def fake_fetch_url(url: str) -> str:
        assert url == "https://example.com/echo.py"
        return ECHO_SCRIPT

    monkeypatch.setattr(
        "screamingface.plugins.python_runner.plugin._fetch_url",
        fake_fetch_url,
    )

    result = await plugin.handle_backend_call(
        json.dumps({"b": 2}),
        sources="https://example.com/echo.py",
        app=app,
    )

    assert json.loads(result) == {"got": {"b": 2}}


@pytest.mark.asyncio
async def test_handle_backend_call_unsupported_scheme_raises_http_400() -> None:
    app = _make_app({"echo": ECHO_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    with pytest.raises(HTTPException) as excinfo:
        await plugin.handle_backend_call(
            "", sources="ftp://example.com/echo.py", app=app
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["kind"] == "io_error"


@pytest.mark.asyncio
async def test_handle_backend_call_syntax_error_surfaces_as_http_500() -> None:
    app = _make_app({"broken": SYNTAX_ERROR_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    with pytest.raises(HTTPException) as excinfo:
        await plugin.handle_backend_call(
            "{}", sources="/data/code/broken.py", app=app
        )
    assert excinfo.value.status_code == 500
    detail = excinfo.value.detail
    assert detail["kind"] == "nonzero_exit"
    assert "SyntaxError" in detail["stderr"]


@pytest.mark.asyncio
async def test_handle_backend_call_fetch_404_propagates_as_http_400() -> None:
    app = _make_app({})  # no scripts: /data/code/missing.py 404s
    plugin = app.state.plugins.active_plugins["python-runner"]

    with pytest.raises(HTTPException) as excinfo:
        await plugin.handle_backend_call(
            "", sources="/data/code/missing.py", app=app
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["kind"] == "io_error"
```

- [ ] **Step 2.2: Run tests, expect failures**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_plugin_dispatch.py -v
```

Expected: 6 errors — `NotImplementedError("Wired in DEMO-013")` from the current stub.

- [ ] **Step 2.3: Implement `handle_backend_call`**

In `apps/server/src/screamingface/plugins/python_runner/plugin.py`, add imports and replace the body:

(a) New imports near the top, alongside the existing imports:

```python
import json
import logging
import time

from fastapi import HTTPException
import httpx

from screamingface.plugins.python_runner.runner import (
    PythonRunnerError,
    run_script_source,
)
from screamingface.plugins.url4_executor.url4_resolve import (
    _fetch_relative,
    _fetch_url,
)
from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced
```

(b) Add a module logger:

```python
logger = logging.getLogger(__name__)
```

(c) Replace the existing `handle_backend_call` body:

```python
    async def handle_backend_call(
        self,
        intent: str,
        *,
        sources: str = "",
        app: FastAPI,
    ) -> str:
        """Fetch the script at ``sources``, run it sandboxed, return JSON.

        ``sources`` is the source URL (relative ``/data/code/<name>.py`` or
        absolute ``http(s)://...``). ``intent`` is the JSON payload that the
        script reads from stdin; an empty string means an empty dict.
        """
        with traced("python.handle_backend_call", kind="internal"):
            set_span_attrs({"python.source_url": sources[:500]})

            try:
                if sources.startswith(("http://", "https://")):
                    source = await _fetch_url(sources)
                elif sources.startswith("/"):
                    source = await _fetch_relative(app, sources)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "kind": "io_error",
                            "message": f"Unsupported source URL scheme: {sources!r}",
                        },
                    )
            except HTTPException:
                raise
            except httpx.HTTPError as e:
                logger.warning("python-runner fetch failed for %s: %s", sources, e)
                raise HTTPException(
                    status_code=400,
                    detail={
                        "kind": "io_error",
                        "message": f"Failed to fetch source {sources!r}: {e}",
                    },
                ) from e

            try:
                payload = json.loads(intent) if intent else {}
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "kind": "io_error",
                        "message": f"intent is not valid JSON: {e}",
                    },
                ) from e

            t0 = time.monotonic()
            try:
                result = await run_script_source(source, payload)
            except PythonRunnerError as e:
                duration_ms = int((time.monotonic() - t0) * 1000)
                set_span_attrs(
                    {
                        "python.duration_ms": duration_ms,
                        "python.exit_code": e.exit_code or -1,
                        "python.error_kind": e.kind,
                    }
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "kind": e.kind,
                        "message": e.message,
                        "stderr": e.stderr,
                    },
                ) from e

            duration_ms = int((time.monotonic() - t0) * 1000)
            set_span_attrs({"python.duration_ms": duration_ms})
            return json.dumps(result)
```

- [ ] **Step 2.4: Run dispatch tests, expect pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_plugin_dispatch.py -v
```

Expected: 6 passed (each runs an actual sandboxed subprocess — on darwin the wrap is in effect, on linux fallback to plain argv).

- [ ] **Step 2.5: Full python_runner suite green**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests -v
```

Expected: 53 passed (47 from Task 1 + 6 new).

- [ ] **Step 2.6: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/python_runner/plugin.py \
        apps/server/src/screamingface/plugins/python_runner/tests/test_plugin_dispatch.py
git commit -m "feat(python-runner): implement handle_backend_call (SF-159)"
```

---

## Task 3: In-process E2E through `/ensemble`

**Files:**
- Create: `apps/server/src/screamingface/plugins/python_runner/tests/test_e2e.py`

This test mounts the *real* FastAPI app and dispatches a URL4 expression that exercises the full path: URL4 parse → backend dispatch → fetch via in-process ASGI → sandbox-wrapped subprocess → JSON response.

- [ ] **Step 3.1: Write the E2E test**

Create `apps/server/src/screamingface/plugins/python_runner/tests/test_e2e.py`:

```python
"""End-to-end test: URL4 backend call → /python → /data/code/{name}.py → run.

Uses the real app and in-process ASGI transport — no live server, no
network. Sandbox wrapping is active on darwin (via SF-158).
"""

from __future__ import annotations

import json

import httpx
import pytest

from screamingface.app import create_app
from screamingface.plugins.python_runner.plugin import PythonRunnerSettings


ECHO_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({"echoed": data}))
"""


@pytest.mark.asyncio
async def test_e2e_url4_dispatch_to_python_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    plugin = app.state.plugins.active_plugins["python-runner"]
    plugin.settings = PythonRunnerSettings(scripts={"echo": ECHO_SCRIPT})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://t", timeout=60
    ) as c:
        url4 = '/python(/data/code/echo.py)!{"x": 1}'
        resp = await c.get("/ensemble", params={"q": url4})

    assert resp.status_code == 200, resp.text
    # /ensemble returns the dispatched result as a string. The python-runner
    # returns json-encoded; ensemble passes it through.
    body = resp.text
    assert '"echoed"' in body
    assert json.loads(body)["echoed"] == {"x": 1}
```

- [ ] **Step 3.2: Run it; iterate on URL4 syntax if needed**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_e2e.py -v
```

If this fails because the URL4 parser doesn't accept `{...}` as an intent, or because `/ensemble` wraps the response differently than expected:

- Inspect how `/ensemble` is wired (`apps/server/src/screamingface/plugins/url4_executor/`).
- Switch to the lower-level entry point if needed (e.g. `POST /url4/resolve` or whatever the existing tests use; see `tests/e2e/test_url4_resolution.py` for working patterns).
- Adjust the URL4 expression to the actually-supported intent syntax (likely `/python(/data/code/echo.py)!{"x":1}` URL-encoded, or `/python(/data/code/echo.py)` with the payload set via a different mechanism).

Document the working syntax in a comment in the test file.

If `/ensemble` requires `POST` and a richer body shape, follow the pattern in `apps/server/tests/e2e/test_ensemble_features.py` which the ticket cites as the mocking pattern.

- [ ] **Step 3.3: Run all python_runner tests + relevant existing tests**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests -v
uv run pytest src/screamingface/plugins/url4_executor/tests -v
```

Expected: 54+ python_runner tests passed; all url4_executor tests still pass.

- [ ] **Step 3.4: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/python_runner/tests/test_e2e.py
git commit -m "test(python-runner): in-process e2e for /python URL4 dispatch (SF-159)"
```

---

## Task 4: Local CI gates + PR

- [ ] **Step 4.1: Run ruff + format**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run ruff check src/screamingface/plugins/python_runner
uv run ruff format --check src/screamingface/plugins/python_runner
```

Fix any issues. If `ruff format` wants to reformat, run `uv run ruff format src/screamingface/plugins/python_runner` and re-stage.

- [ ] **Step 4.2: Run full python_runner suite + sandbox-off regression**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests -v
SF_PYTHON_RUNNER__SANDBOX=off uv run pytest src/screamingface/plugins/python_runner/tests -v
```

Expected: green in both modes.

- [ ] **Step 4.3: Run the full apps/server suite to catch ripple effects**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest 2>&1 | tail -30
```

Expected: same baseline as on `SF-158-subprocess-sandboxing` head (the 2 pre-existing `claude` e2e failures may persist — they're unrelated billing/credential issues, not caused by this PR). If any **new** failure appears, fix it before opening the PR.

- [ ] **Step 4.4: Push + open PR (do not merge)**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin SF-159-python-backend-and-serve-route
gh pr create \
  --base SF-158-subprocess-sandboxing \
  --title "SF-159: wire /python backend + /data/code/{name}.py serve route" \
  --body-file - <<'EOF'
## Summary
- `GET /data/code/{name}.py` serves source from `python-runner.scripts.<name>` settings, 404 on miss
- `PythonRunnerPlugin.handle_backend_call` fetches the source URL (relative via in-process ASGI or absolute HTTP), JSON-parses the intent, runs the script via DEMO-010's `run_script_source` (sandboxed on darwin by SF-158), returns the script's JSON output
- Fetch errors → HTTP 400 `{kind: io_error}`; runner errors → HTTP 500 `{kind, message, stderr}`
- OTel span `python.handle_backend_call` with attrs `python.source_url`, `python.duration_ms`, `python.exit_code` (on failure)
- In-process E2E covers `/ensemble` → `/python(/data/code/<name>.py)!{json}` round-trip

## Spec deviation (called out in plan)

The Asana ticket's example URL4 `(a=1, b=2)!/data/code/check_correct.py` does not match the URL4 grammar. The plugin declares `backend_call_paths = ["/python"]`, so the actual dispatching syntax is `/python(/data/code/<name>.py)!<intent>`. The implementation-side contract in the ticket (`handle_backend_call(intent, sources, app)`) is what we built; the URL4 prose was incorrect.

`get_plugin_settings` from the spec doesn't exist; used `get_plugins_registry(app).active_plugins[...]` instead per `core/admin_router.py`.

## Test plan
- [x] Serve route returns `text/x-python` for known names, 404 for unknown / non-identifier names, reflects settings edits
- [x] `handle_backend_call` handles relative + http(s) sources, empty intent → `{}`, syntax errors surface with stderr, unsupported scheme rejected
- [x] In-process E2E through `/ensemble`
- [x] Existing 43 python_runner tests + all url4_executor tests still pass

Branch is based on `SF-158-subprocess-sandboxing` so the sandbox wrapping is in effect for the new integration tests. Merge SF-158 first, then this.

Closes SF-159.
EOF
```

Stop after PR creation. The user reviews and merges manually.

If the SF-158 PR (#190) has already merged to `main` by the time we push this, change `--base SF-158-subprocess-sandboxing` to `--base main`.

---

## Acceptance criteria mapping

| Ticket criterion | Implemented by |
| --- | --- |
| `GET /data/code/check_correct.py` returns `text/x-python` | Task 1 + `test_serve_known_script_returns_python_source` |
| `GET /data/code/nonexistent.py` returns 404 with clear message | Task 1 + `test_serve_unknown_script_returns_404` |
| `GET /data/code/has-dashes.py` returns 404 | Task 1 + `test_serve_invalid_name_with_dashes_returns_404` |
| Settings edits visible on next request | Task 1 + `test_serve_reflects_settings_edit` |
| `handle_backend_call` with relative source fetches+runs | Task 2 + `test_handle_backend_call_relative_source_runs_and_returns_json` |
| Same with `https://...` works identically | Task 2 + `test_handle_backend_call_http_source_fetched_via_url` |
| SyntaxError surfaces as `PythonRunnerError(kind="nonzero_exit")` with stderr | Task 2 + `test_handle_backend_call_syntax_error_surfaces_as_http_500` |
| Tracing span recorded with `python.source_url`, `python.duration_ms`, `python.exit_code` | Task 2 `traced(...) + set_span_attrs(...)` calls |
| Fetch errors → HTTP 400 `{kind: io_error}` | Task 2 + `test_handle_backend_call_fetch_404_propagates_as_http_400` + `test_handle_backend_call_unsupported_scheme_raises_http_400` |
| Runner errors → HTTP 500 `{kind, stderr}` | Task 2 + `test_handle_backend_call_syntax_error_surfaces_as_http_500` |
| E2E through `/ensemble` | Task 3 + `test_e2e_url4_dispatch_to_python_runner` |
| All existing tests still green | Task 4 Step 4.3 |

## Risks

- **`/ensemble` URL4 surface form.** The Asana ticket's prose example is wrong; the actual URL4 syntax that dispatches into this plugin may need iteration in Task 3 (depending on how `/ensemble` accepts the URL4 string — query param? body? POST? — and how the parser tokenizes the JSON intent). The plan tells the executor to inspect existing `test_url4_resolution.py` / `test_ensemble_features.py` and adapt. If the inline JSON intent doesn't parse, escalate to query-param-encoded form or use a different entry point.
- **`HTTPException` inside `handle_backend_call`.** The url4 dispatcher (`url4_resolve.py:_dispatch_backend_call`) doesn't currently catch `HTTPException`; FastAPI's exception handler still fires because we're inside a request lifecycle. If the call site is invoked outside a request (e.g. from a worker), `HTTPException` won't be translated. The acceptance criteria specifically requires HTTP status codes, so this is the correct surface for the request-path case; if the worker path needs different behavior later, that's a separate ticket.
- **Sandbox-active integration tests on Linux CI.** The new dispatch tests rely on `run_script_source` working at all. On Linux it runs unsandboxed (warning logged once) — the tests still pass because they don't depend on sandbox enforcement, only on the runner.
- **`_fetch_url` / `_fetch_relative` are underscore-prefixed.** They're internal to `url4_executor` but already used by other code paths within the package. If a reviewer pushes back on the cross-plugin import, the fallback is to inline a small fetch helper here (3-5 lines) rather than promote them to public API in a feature PR.
