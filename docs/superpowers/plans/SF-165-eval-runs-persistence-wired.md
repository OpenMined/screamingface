# SF-165 / DEMO-017 — Eval-run persistence wired into `/python` invocations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Asana:** [task 1214568119300254](https://app.asana.com/1/1185126988600652/task/1214568119300254)
- **SF ticket:** SF-165
- **Parent:** [DEMO] Leaderboard Demo — Sergey core track
- **Owner:** A (Sergey)
- **Due:** 2026-05-20
- **Priority:** Medium
- **Estimate:** 1 day
- **Phase / week:** Phase 2, Week 2
- **Dependencies:** SF-159 / DEMO-013 (`/python` backend, `/data/code/...` serve) — open in PR #191; DEMO-014 (`EvalRun`/`EvalQuestion` models + `EvalRunStore`) — landed already.
- **Branch:** `SF-165-eval-runs-persistence-wired` (off `SF-159-python-backend-and-serve-route`)

**Goal:** Wire automatic eval-run persistence into `/python` script invocations so the Eval Studio UI gets one `eval_run` row + N `eval_question` rows for free whenever a request to `/ensemble` carries `X-SF-Run-Id` + `X-SF-Run-Spec` headers — without coupling `python-runner` to the eval domain or making `eval-runs` understand URL4.

**Architecture:** Three loosely-coupled pieces wired through the existing `HookRegistry`:
1. `/ensemble` reads the two headers, mints a `run_id` if absent, injects `__run_id__` + `__run_spec__` into the root `Env`, and emits `eval.run.started` before evaluation / `eval.run.finished` (or `.failed`) after.
2. `python-runner.handle_backend_call` accepts an optional `env: Env | None` keyword (added to the `Plugin.handle_backend_call` contract by widening the dispatcher), reads `__run_id__` from it, and after every successful run whose `sources` matches `*/check_correct.py` emits `eval.question.checked` with the resolved input + output.
3. `eval-runs` plugin gains a `setup` that subscribes its handlers to those four hooks; each handler calls `EvalRunStore` to insert/update rows. The per-run `idx` counter is owned by `eval-runs` (in-memory dict keyed by `run_id`).

**Tech Stack:** FastAPI (header reading), existing `HookRegistry` (`app.state.hooks`), `Env` parent-pointer chain, Tortoise ORM via `EvalRunStore`, `state` plugin for the sqlite lifecycle.

---

## Spec clarifications (call out before implementation)

The Asana ticket conflates two ideas about *which* invocations emit a question hook:

> "Use the resolver's spec_id (the prefix after /data/) for filtering — only hle/check_correct.py and similar emit."

The `python-runner` settings validator (DEMO-009) constrains script keys to `^[a-zA-Z_][a-zA-Z0-9_]*$` — no slashes — and the serve route is `/data/code/{name}.py` (single segment). So a nested path like `/data/code/hle/check_correct.py` is **not reachable** in this codebase. We use the simpler rule the same paragraph allows: emit `eval.question.checked` when `__run_id__` is in `env` **and** the resolved `sources` ends with `/check_correct.py` (the script-name suffix is the convention; the spec name comes from `__run_spec__`).

The ticket also picks design (A) — explicit start/end via the `X-SF-Run-Spec` header. We follow that: no implicit run-from-script-names magic.

`accuracy`, `total_questions`, `correct_questions` on `eval.run.finished` are **computed by the `eval-runs` subscriber** from its own `eval_question` rows when the finished hook fires, not passed in the payload. `/ensemble` doesn't know how many questions were processed.

`eval-runs` is **not** listed in `apps/server/sf.json` yet. Activating it (and adding `state` ahead of it) is part of this plan.

## File structure

- **Modify** `apps/server/src/screamingface/plugins/url4_executor/routes.py` — `/ensemble` reads headers, injects Env bindings, emits run lifecycle hooks.
- **Modify** `apps/server/src/screamingface/plugin.py` — `Plugin.handle_backend_call` signature gains `env: Env | None = None` keyword.
- **Modify** `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py` — `_dispatch_backend_call` passes `env` through to the plugin call.
- **Modify** `apps/server/src/screamingface/plugins/python_runner/plugin.py` — accept `env=`, read `__run_id__`, emit `eval.question.checked` on `check_correct.py`-suffixed runs.
- **Modify** `apps/server/src/screamingface/plugins/eval_runs/plugin.py` — subscribe 4 hooks; in-memory `_question_idx_by_run` counter; finished-handler computes accuracy/totals.
- **Modify** `apps/server/sf.json` — append `state` and `eval-runs` to the active plugin list.
- **Create** `apps/server/src/screamingface/plugins/eval_runs/tests/test_e2e_persistence.py` — full round-trip through `/ensemble` with headers, asserting the sqlite state at end.
- **Create** `apps/server/src/screamingface/plugins/eval_runs/_hook_payloads.py` — `TypedDict` shapes for the four hooks; one source of truth so emitters and subscribers don't drift.
- **Modify** `apps/server/src/screamingface/plugins/python_runner/plugin.py` (existing) — imports `_hook_payloads` and emits using its shape.
- **Modify** `apps/server/src/screamingface/plugins/url4_executor/routes.py` (existing) — same.

The hook-payload module lives under `eval_runs/` not `core/` because the hooks are an `eval-runs` contract — `python-runner` and `url4-executor` *fulfil* it, they don't define it.

---

## Pre-flight

- [ ] **Step 0.1: Confirm branch base**

```bash
cd /Users/sergey/work/openmind/screamingface
git rev-parse --abbrev-ref HEAD
git log --oneline -5
```

Expected: branch `SF-165-eval-runs-persistence-wired`; top of log shows the SF-159 commits (`f98f2af`, `3c8d434`, `3a88a06`, `bd8293d`, …).

- [ ] **Step 0.2: Baseline tests pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests \
              src/screamingface/plugins/url4_executor/tests \
              src/screamingface/plugins/eval_runs/tests -v 2>&1 | tail -5
```

Expected: all passing (266+ tests). If anything fails on the baseline, stop and triage before touching new code.

---

## Task 1: Hook payload shapes + activation in `sf.json`

**Files:**
- Create: `apps/server/src/screamingface/plugins/eval_runs/_hook_payloads.py`
- Modify: `apps/server/sf.json`

- [ ] **Step 1.1: Write `_hook_payloads.py`**

Create `apps/server/src/screamingface/plugins/eval_runs/_hook_payloads.py`:

```python
"""TypedDict payload shapes for the four eval-runs lifecycle hooks.

These are the wire contract between emitters (url4-executor, python-runner)
and the subscriber (eval-runs). Defined here because eval-runs owns the
domain — the emitters just produce events that match these shapes.

Hook names (constants below) are imported by both sides to avoid drift.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

HOOK_RUN_STARTED = "eval.run.started"
HOOK_RUN_FINISHED = "eval.run.finished"
HOOK_RUN_FAILED = "eval.run.failed"
HOOK_QUESTION_CHECKED = "eval.question.checked"


class RunStartedPayload(TypedDict):
    run_id: str
    spec_name: str
    url4_expression: str
    started_at: datetime


class RunFinishedPayload(TypedDict):
    run_id: str
    finished_at: datetime


class RunFailedPayload(TypedDict):
    run_id: str
    finished_at: datetime
    error: str


class QuestionCheckedPayload(TypedDict):
    run_id: str
    question: str
    expected: str
    predicted: str | None
    correct: bool | None
    raw_output: str | None
    error: str | None
```

Note: `idx` is intentionally absent from `QuestionCheckedPayload`. The subscriber owns it (auto-increments per `run_id` to preserve invocation order without coupling the emitter to ordering).

- [ ] **Step 1.2: Append `state` and `eval-runs` to `sf.json`**

Read `apps/server/sf.json` and append `"state"` and `"eval-runs"` to the `plugins` array, in that order (state must come before eval-runs because eval-runs depends on it). Use Edit to insert after the last existing plugin entry. Verify with:

```bash
cd /Users/sergey/work/openmind/screamingface
python3 -c "import json; print(json.load(open('apps/server/sf.json'))['plugins'])"
```

Expected: the printed list ends with `'state', 'eval-runs'` (or those names appear after the existing entries — order matters for dependency resolution).

- [ ] **Step 1.3: Boot smoke**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
SF_STATE__PATH=/tmp/sf-165-smoke.db uv run python -c "
from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
import json
cfg = json.load(open('sf.json'))
config = AppConfig(plugins=cfg['plugins'], plugin_config=cfg.get('plugin_config', {}))
app = create_app(config)
print('active:', sorted(app.state.plugins.active_plugins.keys()))
assert 'eval-runs' in app.state.plugins.active_plugins
print('OK')
"
rm -f /tmp/sf-165-smoke.db
```

Expected: prints `active: [...]` listing both `state` and `eval-runs`, then `OK`. If activation fails on a `depends` constraint, fix the plugin order in `sf.json` before continuing.

- [ ] **Step 1.4: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/_hook_payloads.py apps/server/sf.json
git commit -m "feat(eval-runs): activate plugin + define hook payload contracts (SF-165)"
```

---

## Task 2: `/ensemble` reads headers, emits run lifecycle hooks (TDD)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/routes.py`
- Create: `apps/server/src/screamingface/plugins/url4_executor/tests/test_run_headers.py`

- [ ] **Step 2.1: Failing test — headers absent (no hooks)**

Create `apps/server/src/screamingface/plugins/url4_executor/tests/test_run_headers.py`:

```python
"""Tests for X-SF-Run-Id / X-SF-Run-Spec propagation on /ensemble (SF-165)."""

from __future__ import annotations

import httpx
import pytest

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs._hook_payloads import (
    HOOK_RUN_FAILED,
    HOOK_RUN_FINISHED,
    HOOK_RUN_STARTED,
)


@pytest.fixture
def app_with_executor():
    config = AppConfig(plugins=["url4-executor"], plugin_config={})
    app = create_app(config)
    yield app


@pytest.mark.asyncio
async def test_ensemble_without_headers_does_not_emit_run_hooks(app_with_executor) -> None:
    fired: list[tuple[str, dict]] = []

    def _spy(hook_name: str):
        def _cb(**payload):
            fired.append((hook_name, payload))
        return _cb

    app_with_executor.state.hooks.register(HOOK_RUN_STARTED, _spy(HOOK_RUN_STARTED), plugin_name="spy")
    app_with_executor.state.hooks.register(HOOK_RUN_FINISHED, _spy(HOOK_RUN_FINISHED), plugin_name="spy")
    app_with_executor.state.hooks.register(HOOK_RUN_FAILED, _spy(HOOK_RUN_FAILED), plugin_name="spy")

    transport = httpx.ASGITransport(app=app_with_executor)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/ensemble", params={"q": "hello"})
    assert resp.status_code == 200
    assert fired == []


@pytest.mark.asyncio
async def test_ensemble_with_headers_emits_started_and_finished(app_with_executor) -> None:
    fired: list[tuple[str, dict]] = []

    def _spy(hook_name: str):
        def _cb(**payload):
            fired.append((hook_name, payload))
        return _cb

    app_with_executor.state.hooks.register(HOOK_RUN_STARTED, _spy(HOOK_RUN_STARTED), plugin_name="spy")
    app_with_executor.state.hooks.register(HOOK_RUN_FINISHED, _spy(HOOK_RUN_FINISHED), plugin_name="spy")

    transport = httpx.ASGITransport(app=app_with_executor)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get(
            "/ensemble",
            params={"q": "hello"},
            headers={"X-SF-Run-Id": "11111111-1111-1111-1111-111111111111", "X-SF-Run-Spec": "hle-claude-single"},
        )
    assert resp.status_code == 200

    names = [n for n, _ in fired]
    assert names == [HOOK_RUN_STARTED, HOOK_RUN_FINISHED]

    started_payload = fired[0][1]
    assert started_payload["run_id"] == "11111111-1111-1111-1111-111111111111"
    assert started_payload["spec_name"] == "hle-claude-single"
    assert started_payload["url4_expression"] == "hello"
    assert "started_at" in started_payload

    finished_payload = fired[1][1]
    assert finished_payload["run_id"] == "11111111-1111-1111-1111-111111111111"
    assert "finished_at" in finished_payload


@pytest.mark.asyncio
async def test_ensemble_with_headers_emits_failed_on_exception(app_with_executor) -> None:
    fired: list[tuple[str, dict]] = []

    def _spy(hook_name: str):
        def _cb(**payload):
            fired.append((hook_name, payload))
        return _cb

    app_with_executor.state.hooks.register(HOOK_RUN_STARTED, _spy(HOOK_RUN_STARTED), plugin_name="spy")
    app_with_executor.state.hooks.register(HOOK_RUN_FAILED, _spy(HOOK_RUN_FAILED), plugin_name="spy")

    transport = httpx.ASGITransport(app=app_with_executor)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        # /python is not active here, so the backend call fails with 502.
        resp = await c.get(
            "/ensemble",
            params={"q": "/python(/data/code/x.py)!{}"},
            headers={"X-SF-Run-Id": "22222222-2222-2222-2222-222222222222", "X-SF-Run-Spec": "x"},
        )
    assert resp.status_code == 502

    names = [n for n, _ in fired]
    assert names == [HOOK_RUN_STARTED, HOOK_RUN_FAILED]
    assert fired[1][1]["run_id"] == "22222222-2222-2222-2222-222222222222"
    assert "error" in fired[1][1]


@pytest.mark.asyncio
async def test_ensemble_mints_run_id_when_only_spec_present(app_with_executor) -> None:
    fired: list[tuple[str, dict]] = []

    def _spy(hook_name: str):
        def _cb(**payload):
            fired.append((hook_name, payload))
        return _cb

    app_with_executor.state.hooks.register(HOOK_RUN_STARTED, _spy(HOOK_RUN_STARTED), plugin_name="spy")

    transport = httpx.ASGITransport(app=app_with_executor)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get(
            "/ensemble",
            params={"q": "hello"},
            headers={"X-SF-Run-Spec": "ad-hoc"},
        )
    assert resp.status_code == 200
    assert len(fired) == 1
    started = fired[0][1]
    # mint a uuid4 — 36 chars with hyphens.
    assert len(started["run_id"]) == 36
    assert started["run_id"].count("-") == 4
    assert started["spec_name"] == "ad-hoc"
```

- [ ] **Step 2.2: Verify failure**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_run_headers.py -v
```

Expected: 4 failures — `/ensemble` doesn't read headers or emit hooks yet.

- [ ] **Step 2.3: Implement header handling + hook emission in `routes.py`**

Edit `apps/server/src/screamingface/plugins/url4_executor/routes.py`. Add imports near the existing ones:

```python
import uuid
from datetime import datetime, timezone

from fastapi import Header

from screamingface.plugins.eval_runs._hook_payloads import (
    HOOK_RUN_FAILED,
    HOOK_RUN_FINISHED,
    HOOK_RUN_STARTED,
)
from screamingface.plugins.url4_executor.scope import Env
```

Replace the existing `url4_resolve` handler signature and body. Current code is roughly:

```python
    @router.get("/ensemble", response_model=None, operation_id="url4_resolve")
    async def url4_resolve(
        q: str | None = None,
        ast: bool = False,
        processor: str | None = None,
    ) -> PlainTextResponse | JSONResponse:
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'q' query parameter")
        interpreter = EnsembleInterpreter(app=app, processor=processor)
        try:
            result = await interpreter.evaluate(q, env=Env.root())
        except Exception as exc:
            logger.warning("url4 evaluation failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"url4 evaluation failed: {exc}")
        ...
```

Change to:

```python
    @router.get("/ensemble", response_model=None, operation_id="url4_resolve")
    async def url4_resolve(
        request: Request,
        q: str | None = None,
        ast: bool = False,
        processor: str | None = None,
        x_sf_run_id: str | None = Header(default=None, alias="X-SF-Run-Id"),
        x_sf_run_spec: str | None = Header(default=None, alias="X-SF-Run-Spec"),
    ) -> PlainTextResponse | JSONResponse:
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'q' query parameter")

        # Mint run_id if any eval headers are present.
        run_id: str | None = None
        if x_sf_run_id or x_sf_run_spec:
            run_id = x_sf_run_id or str(uuid.uuid4())

        env = Env.root()
        if run_id:
            env = env.child(__run_id__=run_id, __run_spec__=x_sf_run_spec or "")
            await request.app.state.hooks.emit_async(
                HOOK_RUN_STARTED,
                run_id=run_id,
                spec_name=x_sf_run_spec or "",
                url4_expression=q,
                started_at=datetime.now(timezone.utc),
            )

        interpreter = EnsembleInterpreter(app=app, processor=processor)

        try:
            result = await interpreter.evaluate(q, env=env)
        except Exception as exc:
            logger.warning("url4 evaluation failed: %s", exc, exc_info=True)
            if run_id:
                await request.app.state.hooks.emit_async(
                    HOOK_RUN_FAILED,
                    run_id=run_id,
                    finished_at=datetime.now(timezone.utc),
                    error=str(exc),
                )
            raise HTTPException(status_code=502, detail=f"url4 evaluation failed: {exc}")

        if run_id:
            await request.app.state.hooks.emit_async(
                HOOK_RUN_FINISHED,
                run_id=run_id,
                finished_at=datetime.now(timezone.utc),
            )

        # (existing tracing + response logic unchanged below)
```

You also need to add `Request` to the existing `from fastapi import` line (it currently imports `APIRouter, HTTPException`).

Leave the rest of the handler (tracing, ast response, body) untouched — only the env construction and hook calls change.

- [ ] **Step 2.4: Verify pass**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_run_headers.py -v
```

Expected: 4 passed.

- [ ] **Step 2.5: Full url4_executor regression**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests -v 2>&1 | tail -5
```

Expected: all existing url4_executor tests still pass.

- [ ] **Step 2.6: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/url4_executor/routes.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_run_headers.py
git commit -m "feat(url4-executor): emit run.started/.finished/.failed from /ensemble (SF-165)"
```

---

## Task 3: Widen `Plugin.handle_backend_call` to accept `env=` (TDD)

**Files:**
- Modify: `apps/server/src/screamingface/plugin.py`
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`
- Modify: `apps/server/src/screamingface/plugins/python_runner/plugin.py` (signature only — body change is Task 4)
- Modify: every other plugin overriding `handle_backend_call` (none currently call out the `env` keyword; the default-value addition is backwards-compatible).

- [ ] **Step 3.1: Failing test — env reaches the plugin**

Append to `apps/server/src/screamingface/plugins/url4_executor/tests/test_url4.py` (or create a new `tests/test_dispatch_env.py` if you prefer isolation — create the new file for clarity):

Create `apps/server/src/screamingface/plugins/url4_executor/tests/test_dispatch_env.py`:

```python
"""Test that _dispatch_backend_call forwards `env` to handle_backend_call (SF-165)."""

from __future__ import annotations

import pytest

from screamingface.plugin import Plugin
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4 import Url4BackendCall, Url4Text
from screamingface.plugins.url4_executor.url4_resolve import _dispatch_backend_call


class _SpyPlugin(Plugin):
    name = "spy"
    backend_call_paths = ["/spy"]

    def __init__(self) -> None:
        self.received_env: Env | None = None

    async def handle_backend_call(self, intent, *, sources="", app, env=None):
        self.received_env = env
        return "ok"


class _Registry:
    def __init__(self, plugin):
        self.active_plugins = {"spy": plugin}


@pytest.mark.asyncio
async def test_dispatch_forwards_env_to_plugin():
    from fastapi import FastAPI

    app = FastAPI()
    plugin = _SpyPlugin()
    app.state.plugins = _Registry(plugin)

    env = Env.root().child(__run_id__="abc", __run_spec__="hle-x")
    node = Url4BackendCall(path="/spy", intent=Url4Text(value="payload"))

    await _dispatch_backend_call(node, app, env)

    assert plugin.received_env is not None
    assert plugin.received_env.lookup("__run_id__") == "abc"
    assert plugin.received_env.lookup("__run_spec__") == "hle-x"
```

- [ ] **Step 3.2: Verify failure**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_dispatch_env.py -v
```

Expected: FAIL — `_dispatch_backend_call` currently calls `plugin.handle_backend_call(intent_text, sources=sources_text, app=app)` without `env=`, and `Plugin.handle_backend_call` doesn't accept `env=`.

- [ ] **Step 3.3: Widen the base contract**

In `apps/server/src/screamingface/plugin.py`, find the `Plugin` class's `handle_backend_call` method (or its default) and add an optional `env` keyword. The default base method should accept and ignore `env`:

```python
    async def handle_backend_call(
        self,
        intent: str,
        *,
        sources: str = "",
        app: "FastAPI",
        env: "Env | None" = None,
    ) -> str:
        del intent, sources, app, env
        raise NotImplementedError(f"{type(self).__name__} did not implement handle_backend_call")
```

Add `if TYPE_CHECKING: from screamingface.plugins.url4_executor.scope import Env` at the top of `plugin.py` if not already present.

- [ ] **Step 3.4: Pass `env` through the dispatcher**

In `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`, change the call site at the matching path. Current:

```python
            return await plugin.handle_backend_call(intent_text, sources=sources_text, app=app)
```

New:

```python
            return await plugin.handle_backend_call(intent_text, sources=sources_text, app=app, env=env)
```

- [ ] **Step 3.5: Update `PythonRunnerPlugin.handle_backend_call` signature only**

In `apps/server/src/screamingface/plugins/python_runner/plugin.py`, add `env: "Env | None" = None` to the keyword arguments of `handle_backend_call`. Body is unchanged in this task — just the signature.

```python
    async def handle_backend_call(
        self,
        intent: str,
        *,
        sources: str = "",
        app: FastAPI,
        env: Env | None = None,
    ) -> str:
        ...
```

Add the import: `from screamingface.plugins.url4_executor.scope import Env` (top-level; we'll use it in Task 4).

- [ ] **Step 3.6: Verify dispatch test passes**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests/test_dispatch_env.py -v
uv run pytest src/screamingface/plugins/python_runner/tests -v 2>&1 | tail -5
```

Expected: dispatch test passes; all 54 python_runner tests still pass (signature widening is backwards-compatible).

- [ ] **Step 3.7: Scan for other plugins implementing `handle_backend_call`**

```bash
cd /Users/sergey/work/openmind/screamingface
grep -rn "async def handle_backend_call" apps/server/src/screamingface/plugins/
```

For each match outside `python_runner` and the base `plugin.py`, add `env: "Env | None" = None` to the signature so the dispatcher's new keyword call doesn't break them. Body changes are out of scope — just the signature.

If grep returns only the base + `python_runner`, no other edits needed.

- [ ] **Step 3.8: Full url4_executor + every backend plugin regression**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/url4_executor/tests \
              src/screamingface/plugins/python_runner/tests -v 2>&1 | tail -5
# Also each other plugin whose handle_backend_call was widened:
uv run pytest src/screamingface/plugins -v 2>&1 | tail -5
```

Expected: green throughout.

- [ ] **Step 3.9: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugin.py \
        apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py \
        apps/server/src/screamingface/plugins/python_runner/plugin.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_dispatch_env.py
# Plus any other plugin files touched in Step 3.7:
# git add apps/server/src/screamingface/plugins/<other>/plugin.py
git commit -m "feat(plugin): widen handle_backend_call to accept env keyword (SF-165)"
```

---

## Task 4: `python-runner` emits `eval.question.checked` (TDD)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/python_runner/plugin.py`
- Create: `apps/server/src/screamingface/plugins/python_runner/tests/test_question_hook.py`

- [ ] **Step 4.1: Failing tests**

Create `apps/server/src/screamingface/plugins/python_runner/tests/test_question_hook.py`:

```python
"""Tests for python-runner emitting eval.question.checked (SF-165)."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI

from screamingface.core.hooks import HookRegistry
from screamingface.plugins.eval_runs._hook_payloads import HOOK_QUESTION_CHECKED
from screamingface.plugins.python_runner.plugin import (
    PythonRunnerPlugin,
    PythonRunnerSettings,
)
from screamingface.plugins.python_runner.routes import create_router
from screamingface.plugins.url4_executor.scope import Env


CHECK_CORRECT_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({
    "question": data.get("question", ""),
    "expected": data.get("expected", ""),
    "predicted": data.get("predicted", ""),
    "correct": data.get("predicted") == data.get("expected"),
    "raw_output": data.get("predicted", ""),
}))
"""

ECHO_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({"got": data}))
"""


def _make_app(scripts: dict[str, str]) -> FastAPI:
    app = FastAPI()
    plugin = PythonRunnerPlugin()
    plugin.settings = PythonRunnerSettings(scripts=scripts)

    class _Registry:
        active_plugins = {"python-runner": plugin}

    app.state.plugins = _Registry()
    app.state.hooks = HookRegistry()
    app.include_router(create_router(app))
    return app


@pytest.mark.asyncio
async def test_check_correct_invocation_with_run_id_emits_question_checked() -> None:
    app = _make_app({"check_correct": CHECK_CORRECT_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    fired: list[dict] = []
    app.state.hooks.register(
        HOOK_QUESTION_CHECKED,
        lambda **payload: fired.append(payload),
        plugin_name="spy",
    )

    payload = {"question": "2+2", "expected": "4", "predicted": "4"}
    env = Env.root().child(__run_id__="abc", __run_spec__="hle")

    await plugin.handle_backend_call(
        json.dumps(payload),
        sources="/data/code/check_correct.py",
        app=app,
        env=env,
    )

    assert len(fired) == 1
    ev = fired[0]
    assert ev["run_id"] == "abc"
    assert ev["question"] == "2+2"
    assert ev["expected"] == "4"
    assert ev["predicted"] == "4"
    assert ev["correct"] is True
    assert ev["error"] is None


@pytest.mark.asyncio
async def test_check_correct_without_run_id_does_not_emit() -> None:
    app = _make_app({"check_correct": CHECK_CORRECT_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    fired: list[dict] = []
    app.state.hooks.register(
        HOOK_QUESTION_CHECKED,
        lambda **payload: fired.append(payload),
        plugin_name="spy",
    )

    await plugin.handle_backend_call(
        json.dumps({"question": "q", "expected": "e", "predicted": "p"}),
        sources="/data/code/check_correct.py",
        app=app,
        env=None,
    )

    assert fired == []


@pytest.mark.asyncio
async def test_non_check_correct_script_with_run_id_does_not_emit() -> None:
    app = _make_app({"echo": ECHO_SCRIPT})
    plugin = app.state.plugins.active_plugins["python-runner"]

    fired: list[dict] = []
    app.state.hooks.register(
        HOOK_QUESTION_CHECKED,
        lambda **payload: fired.append(payload),
        plugin_name="spy",
    )

    env = Env.root().child(__run_id__="abc", __run_spec__="hle")
    await plugin.handle_backend_call(
        json.dumps({"x": 1}),
        sources="/data/code/echo.py",
        app=app,
        env=env,
    )

    assert fired == []
```

- [ ] **Step 4.2: Verify failures**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_question_hook.py -v
```

Expected: 1 failure (`test_check_correct_invocation_with_run_id_emits_question_checked` — no hook fires); the other two pass vacuously (no hook is implemented yet, so empty `fired` matches expectation).

- [ ] **Step 4.3: Emit the hook in `handle_backend_call`**

Edit `apps/server/src/screamingface/plugins/python_runner/plugin.py`. Add import:

```python
from screamingface.plugins.eval_runs._hook_payloads import HOOK_QUESTION_CHECKED
```

Inside `handle_backend_call`, after the successful `run_script_source` call (right before `return json.dumps(result)`), add the conditional hook emission:

```python
            # eval-runs integration: emit question.checked when this run has
            # a __run_id__ in env AND the script is a check_correct.py-shaped
            # invocation. Other scripts and untagged calls don't touch the
            # eval pipeline.
            run_id = env.lookup("__run_id__") if env else None
            if isinstance(run_id, str) and sources.endswith("/check_correct.py"):
                question = ""
                expected = ""
                try:
                    payload_obj = json.loads(intent) if intent else {}
                    if isinstance(payload_obj, dict):
                        question = str(payload_obj.get("question", ""))
                        expected = str(payload_obj.get("expected", ""))
                except (json.JSONDecodeError, TypeError):
                    pass

                if not isinstance(result, dict):
                    result_dict: dict = {}
                else:
                    result_dict = result

                await app.state.hooks.emit_async(
                    HOOK_QUESTION_CHECKED,
                    run_id=run_id,
                    question=question,
                    expected=expected,
                    predicted=result_dict.get("predicted"),
                    correct=result_dict.get("correct"),
                    raw_output=result_dict.get("raw_output"),
                    error=None,
                )
```

Wrap the `env.lookup` in a try/except KeyError too — Env raises KeyError on miss:

```python
            run_id = None
            if env is not None:
                try:
                    run_id = env.lookup("__run_id__")
                except KeyError:
                    run_id = None
```

Then the `isinstance(run_id, str)` check covers both None and missing.

- [ ] **Step 4.4: Verify pass**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_question_hook.py -v
```

Expected: 3 passed.

- [ ] **Step 4.5: Full python_runner regression**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests -v 2>&1 | tail -5
```

Expected: 57 passed (54 baseline + 3 new). The existing dispatch tests don't pass `env=`, which means `env` defaults to `None` and the new emission block is skipped — verifying backwards compatibility.

- [ ] **Step 4.6: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/python_runner/plugin.py \
        apps/server/src/screamingface/plugins/python_runner/tests/test_question_hook.py
git commit -m "feat(python-runner): emit eval.question.checked when run_id+check_correct (SF-165)"
```

---

## Task 5: `eval-runs` subscribes + persists (TDD)

**Files:**
- Modify: `apps/server/src/screamingface/plugins/eval_runs/plugin.py`
- Create: `apps/server/src/screamingface/plugins/eval_runs/tests/test_hook_subscribers.py`

- [ ] **Step 5.1: Failing test — subscribers write rows on hook emission**

Create `apps/server/src/screamingface/plugins/eval_runs/tests/test_hook_subscribers.py`:

```python
"""Direct hook-driven persistence tests for eval-runs (SF-165).

These exercise the subscribers without driving them through /ensemble —
gives a small surface and fast feedback. Full /ensemble round-trip is
covered in test_e2e_persistence.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs._hook_payloads import (
    HOOK_QUESTION_CHECKED,
    HOOK_RUN_FAILED,
    HOOK_RUN_FINISHED,
    HOOK_RUN_STARTED,
)
from screamingface.plugins.eval_runs.models import EvalQuestion, EvalRun


@pytest.fixture
def temp_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "state.db"
    monkeypatch.setenv("SF_STATE__PATH", str(db))
    return db


@pytest.fixture
async def app_with_eval_runs(temp_state_path: Path):
    config = AppConfig(plugins=["state", "eval-runs"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        yield app


@pytest.mark.asyncio
async def test_run_started_inserts_running_row(app_with_eval_runs: FastAPI) -> None:
    run_id = str(uuid4())
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name="hle-claude",
        url4_expression="hello",
        started_at=datetime.now(timezone.utc),
    )
    row = await EvalRun.get(id=run_id)
    assert row.spec_name == "hle-claude"
    assert row.status == "running"
    assert row.url4_expression == "hello"
    assert row.accuracy is None


@pytest.mark.asyncio
async def test_question_checked_inserts_eval_question_row(
    app_with_eval_runs: FastAPI,
) -> None:
    run_id = str(uuid4())
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name="hle",
        url4_expression="x",
        started_at=datetime.now(timezone.utc),
    )

    for i in range(3):
        await app_with_eval_runs.state.hooks.emit_async(
            HOOK_QUESTION_CHECKED,
            run_id=run_id,
            question=f"q{i}",
            expected=str(i),
            predicted=str(i),
            correct=True,
            raw_output=str(i),
            error=None,
        )

    questions = await EvalQuestion.filter(run_id=run_id).order_by("idx")
    assert [q.idx for q in questions] == [0, 1, 2]
    assert [q.question for q in questions] == ["q0", "q1", "q2"]
    assert all(q.correct for q in questions)


@pytest.mark.asyncio
async def test_run_finished_computes_accuracy_and_marks_done(
    app_with_eval_runs: FastAPI,
) -> None:
    run_id = str(uuid4())
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name="hle",
        url4_expression="x",
        started_at=datetime.now(timezone.utc),
    )
    for i, correct in enumerate([True, True, False, True, False]):
        await app_with_eval_runs.state.hooks.emit_async(
            HOOK_QUESTION_CHECKED,
            run_id=run_id,
            question=f"q{i}",
            expected="e",
            predicted="p",
            correct=correct,
            raw_output="r",
            error=None,
        )

    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_FINISHED,
        run_id=run_id,
        finished_at=datetime.now(timezone.utc),
    )

    row = await EvalRun.get(id=run_id)
    assert row.status == "done"
    assert row.total_questions == 5
    assert row.correct_questions == 3
    assert row.accuracy == pytest.approx(0.6)
    assert row.finished_at is not None


@pytest.mark.asyncio
async def test_run_failed_marks_failed_with_error(app_with_eval_runs: FastAPI) -> None:
    run_id = str(uuid4())
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_STARTED,
        run_id=run_id,
        spec_name="hle",
        url4_expression="x",
        started_at=datetime.now(timezone.utc),
    )
    await app_with_eval_runs.state.hooks.emit_async(
        HOOK_RUN_FAILED,
        run_id=run_id,
        finished_at=datetime.now(timezone.utc),
        error="boom",
    )

    row = await EvalRun.get(id=run_id)
    assert row.status == "failed"
    assert row.error == "boom"
    assert row.finished_at is not None
```

- [ ] **Step 5.2: Verify failure**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_hook_subscribers.py -v
```

Expected: 4 failures — `EvalRun.get(id=run_id)` raises `DoesNotExist` because no subscribers are registered yet.

- [ ] **Step 5.3: Implement subscribers in `eval_runs/plugin.py`**

Edit `apps/server/src/screamingface/plugins/eval_runs/plugin.py`. In `setup`, after the existing `state.register_models(...)` and `app.state.eval_run_store = ...` lines, register four hook handlers. Add a class-level `_question_idx_by_run: dict[str, int] = {}` for the in-memory counter.

Full updated `setup` body:

```python
    _question_idx_by_run: dict[str, int]

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        from screamingface.plugins.eval_runs._hook_payloads import (
            HOOK_QUESTION_CHECKED,
            HOOK_RUN_FAILED,
            HOOK_RUN_FINISHED,
            HOOK_RUN_STARTED,
        )
        from screamingface.plugins.eval_runs.models import EvalQuestion, EvalRun

        state = app.state.state_plugin
        state.register_models(
            "eval_runs",
            ["screamingface.plugins.eval_runs.models"],
        )

        app.state.eval_run_store = EvalRunStore()

        router = create_router()
        routes.add_router(self.name, router, prefix="")

        self._question_idx_by_run = {}

        async def _on_run_started(**payload) -> None:
            await EvalRun.create(
                id=payload["run_id"],
                spec_name=payload["spec_name"],
                url4_expression=payload["url4_expression"],
                started_at=payload["started_at"],
                status="running",
            )
            self._question_idx_by_run[payload["run_id"]] = 0

        async def _on_question_checked(**payload) -> None:
            run_id = payload["run_id"]
            idx = self._question_idx_by_run.get(run_id, 0)
            self._question_idx_by_run[run_id] = idx + 1
            run = await EvalRun.get_or_none(id=run_id)
            if run is None:
                return  # orphan question (no started hook) — ignore.
            await EvalQuestion.create(
                run=run,
                idx=idx,
                question=payload["question"],
                expected=payload["expected"],
                predicted=payload.get("predicted"),
                correct=payload.get("correct"),
                raw_output=payload.get("raw_output"),
                error=payload.get("error"),
            )

        async def _on_run_finished(**payload) -> None:
            run_id = payload["run_id"]
            total = await EvalQuestion.filter(run_id=run_id).count()
            correct = await EvalQuestion.filter(run_id=run_id, correct=True).count()
            accuracy = (correct / total) if total else 0.0
            await EvalRun.filter(id=run_id).update(
                status="done",
                finished_at=payload["finished_at"],
                accuracy=accuracy,
                total_questions=total,
                correct_questions=correct,
            )
            self._question_idx_by_run.pop(run_id, None)

        async def _on_run_failed(**payload) -> None:
            run_id = payload["run_id"]
            await EvalRun.filter(id=run_id).update(
                status="failed",
                finished_at=payload["finished_at"],
                error=payload.get("error"),
            )
            self._question_idx_by_run.pop(run_id, None)

        hooks.register(HOOK_RUN_STARTED, _on_run_started, plugin_name=self.name)
        hooks.register(HOOK_QUESTION_CHECKED, _on_question_checked, plugin_name=self.name)
        hooks.register(HOOK_RUN_FINISHED, _on_run_finished, plugin_name=self.name)
        hooks.register(HOOK_RUN_FAILED, _on_run_failed, plugin_name=self.name)
```

If `EvalRun.id` is a `UUIDField` (check the BaseModel mixin in `screamingface.plugins.state.base`), pass `payload["run_id"]` as a `str` and let Tortoise coerce. If Tortoise rejects the string, wrap with `uuid.UUID(payload["run_id"])`.

- [ ] **Step 5.4: Verify pass**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_hook_subscribers.py -v
```

Expected: 4 passed.

- [ ] **Step 5.5: Existing eval_runs tests still green**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests -v 2>&1 | tail -5
```

Expected: all eval_runs tests pass (existing 23 + new 4 = 27).

- [ ] **Step 5.6: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/plugin.py \
        apps/server/src/screamingface/plugins/eval_runs/tests/test_hook_subscribers.py
git commit -m "feat(eval-runs): subscribe to run + question hooks and persist (SF-165)"
```

---

## Task 6: End-to-end persistence test through `/ensemble`

**Files:**
- Create: `apps/server/src/screamingface/plugins/eval_runs/tests/test_e2e_persistence.py`

- [ ] **Step 6.1: Write the e2e test**

Create `apps/server/src/screamingface/plugins/eval_runs/tests/test_e2e_persistence.py`:

```python
"""End-to-end: /ensemble with run headers persists one eval_run + N eval_questions (SF-165).

Drives the full path through url4-executor → python-runner → eval-runs
subscribers, in-process via httpx.ASGITransport.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs.models import EvalQuestion, EvalRun
from screamingface.plugins.python_runner.plugin import PythonRunnerSettings


CHECK_CORRECT_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
print(json.dumps({
    "question": data["question"],
    "expected": data["expected"],
    "predicted": data["predicted"],
    "correct": data["predicted"] == data["expected"],
    "raw_output": data["predicted"],
}))
"""


@pytest.fixture
def temp_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "state.db"
    monkeypatch.setenv("SF_STATE__PATH", str(db))
    return db


@pytest.fixture
async def app_full(temp_state_path: Path):
    config = AppConfig(
        plugins=["state", "url4-executor", "python-runner", "eval-runs"],
        plugin_config={},
    )
    app = create_app(config)
    async with app.router.lifespan_context(app):
        plugin = app.state.plugins.active_plugins["python-runner"]
        plugin.settings = PythonRunnerSettings(scripts={"check_correct": CHECK_CORRECT_SCRIPT})
        yield app


@pytest.mark.asyncio
async def test_e2e_one_question_persists(app_full) -> None:
    run_id = str(uuid4())
    payload = {"question": "2+2", "expected": "4", "predicted": "4"}
    url4 = f'(/python(/data/code/check_correct.py)!{json.dumps(payload, separators=(",", ":"))})'

    transport = httpx.ASGITransport(app=app_full)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=60) as c:
        resp = await c.get(
            "/ensemble",
            params={"q": url4},
            headers={"X-SF-Run-Id": run_id, "X-SF-Run-Spec": "hle-claude-single"},
        )
    assert resp.status_code == 200, resp.text

    run = await EvalRun.get(id=run_id)
    assert run.status == "done"
    assert run.spec_name == "hle-claude-single"
    assert run.total_questions == 1
    assert run.correct_questions == 1
    assert run.accuracy == pytest.approx(1.0)

    questions = await EvalQuestion.filter(run_id=run_id)
    assert len(questions) == 1
    assert questions[0].question == "2+2"
    assert questions[0].correct is True


@pytest.mark.asyncio
async def test_e2e_without_headers_persists_nothing(app_full) -> None:
    payload = {"question": "q", "expected": "e", "predicted": "e"}
    url4 = f'(/python(/data/code/check_correct.py)!{json.dumps(payload, separators=(",", ":"))})'

    transport = httpx.ASGITransport(app=app_full)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=60) as c:
        resp = await c.get("/ensemble", params={"q": url4})
    assert resp.status_code == 200

    assert await EvalRun.all().count() == 0
    assert await EvalQuestion.all().count() == 0
```

The 5-row scenario from the spec is structurally identical — sending five separate `/ensemble` requests with the same `X-SF-Run-Id` would need the run to span multiple requests, which the design (one request = one run, started/finished bracketing the evaluation) doesn't support. The single-request fan-out (one URL4 expression evaluating five questions in one pass) is the right shape, but the URL4 grammar for that fan-out is a separate concern (DEMO-006 / collection iteration) — out of scope here. One question per run exercises every code path; five would only multiply, not reveal new behavior.

- [ ] **Step 6.2: Run the e2e test**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/eval_runs/tests/test_e2e_persistence.py -v
```

Expected: 2 passed. If the URL4 parsing of inline JSON intent fails (similar to SF-159 Task 3's `split_intent` problem), fall back to a single-key non-JSON payload OR a `()`-wrapped form that survives ensemble's intent splitter. Document any deviation as a comment in the test.

- [ ] **Step 6.3: Full server-side regression**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests \
              src/screamingface/plugins/url4_executor/tests \
              src/screamingface/plugins/eval_runs/tests -v 2>&1 | tail -5
```

Expected: all green (≈ 270 tests).

- [ ] **Step 6.4: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/eval_runs/tests/test_e2e_persistence.py
git commit -m "test(eval-runs): e2e persistence through /ensemble (SF-165)"
```

---

## Task 7: Local CI gates + PR

- [ ] **Step 7.1: Lint**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run ruff check src/screamingface/plugins/eval_runs \
                  src/screamingface/plugins/url4_executor \
                  src/screamingface/plugins/python_runner \
                  src/screamingface/plugin.py
uv run ruff format --check src/screamingface/plugins/eval_runs \
                            src/screamingface/plugins/url4_executor \
                            src/screamingface/plugins/python_runner \
                            src/screamingface/plugin.py
```

Fix any complaints.

- [ ] **Step 7.2: Full server suite for ripple effects**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest 2>&1 | tail -10
```

Expected: only the two pre-existing `tests/e2e/test_url4_resolution.py::TestUrl4IntentDispatch` failures (502 from `/claude/default`, OAuth/billing — also on `main`). No new failures.

- [ ] **Step 7.3: Push + open PR (base = SF-159 branch)**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin SF-165-eval-runs-persistence-wired
gh pr create \
  --base SF-159-python-backend-and-serve-route \
  --title "SF-165: wire eval-runs persistence into /python invocations" \
  --body-file - <<'EOF'
## Summary
- `/ensemble` reads `X-SF-Run-Id` + `X-SF-Run-Spec` headers; mints a uuid4 run_id if only spec given; injects `__run_id__` + `__run_spec__` into the root Env.
- Emits `eval.run.started` / `eval.run.finished` (success) / `eval.run.failed` (exception) hooks bracketing evaluation.
- `Plugin.handle_backend_call` widened with an optional `env=` keyword; `_dispatch_backend_call` forwards env to plugins.
- `python-runner.handle_backend_call` emits `eval.question.checked` when env carries `__run_id__` AND sources ends with `/check_correct.py`.
- `eval-runs` plugin subscribes to all four hooks; persists rows; computes accuracy/totals from its own `eval_question` rows on the finished hook.
- `state` and `eval-runs` activated in `apps/server/sf.json`.

## Spec deviations (called out in plan)
1. **Spec_id from path** is impossible — `python-runner` validates script names against `^[a-zA-Z_][a-zA-Z0-9_]*$` and the serve route is single-segment, so `/data/code/hle/check_correct.py` is unreachable. The script-suffix rule (`endswith("/check_correct.py")`) replaces the spec_id-from-path filter. `__run_spec__` covers the spec_name need.
2. **`idx` is owned by the subscriber** — the spec listed `idx` on the question payload, but the emitter doesn't know the run-relative ordering. The subscriber maintains an in-memory `{run_id: counter}` and auto-increments. Survives a server restart only via reaping orphan `running` rows (out of scope for this ticket).
3. **`accuracy`/`total_questions`/`correct_questions`** are computed by the subscriber on the finished hook, not passed in the payload — `/ensemble` doesn't know.

## Test plan
- [x] `/ensemble` emits zero hooks without headers
- [x] `/ensemble` emits run_started + run_finished with full payload when both headers present
- [x] `/ensemble` emits run_started + run_failed when evaluation throws
- [x] `/ensemble` mints a uuid4 when only X-SF-Run-Spec given
- [x] Dispatcher forwards env to handle_backend_call
- [x] python-runner emits question.checked on check_correct.py runs when env has run_id
- [x] python-runner skips emission for non-check_correct scripts and for missing run_id
- [x] eval-runs subscribers insert/update rows for all four hooks; accuracy computed correctly
- [x] E2E through /ensemble with headers persists 1 eval_run + 1 eval_question
- [x] E2E without headers persists nothing (purity regression)

Branch is based on `SF-159-python-backend-and-serve-route` (#191). Merge SF-159 first, then this.

Plan: `docs/superpowers/plans/SF-165-eval-runs-persistence-wired.md`.

Closes SF-165.
EOF
```

Stop after PR creation. The user reviews and merges manually.

If `SF-159-python-backend-and-serve-route` has already merged to `main` when we push, change `--base` to `main`.

---

## Acceptance criteria mapping

| Ticket criterion | Implemented by |
| --- | --- |
| `/ensemble` accepts `X-SF-Run-Id` and `X-SF-Run-Spec` headers | Task 2 + `test_ensemble_with_headers_emits_started_and_finished` |
| Headers visible via Env reserved bindings `__run_id__` / `__run_spec__` | Task 2 (Env child) + Task 3 (`test_dispatch_forwards_env_to_plugin`) |
| `eval.run.started` fires on entry when headers present; row inserted | Task 2 emit + Task 5 `_on_run_started` + `test_run_started_inserts_running_row` |
| `eval.question.checked` fires per check_correct.py run; row inserted | Task 4 + Task 5 + `test_question_checked_inserts_eval_question_row` |
| `eval.run.finished` on success; status=done, accuracy, totals | Task 2 + Task 5 + `test_run_finished_computes_accuracy_and_marks_done` |
| `eval.run.failed` on exception; status=failed, error | Task 2 + Task 5 + `test_run_failed_marks_failed_with_error` |
| E2E test: headers + sample → 1 eval_run + N eval_questions, accuracy matches | Task 6 + `test_e2e_one_question_persists` |
| Without headers, no eval_runs rows (regression sanity) | Task 6 + `test_e2e_without_headers_persists_nothing` |

## Risks

- **`Plugin.handle_backend_call` signature change is global.** Every plugin overriding it needs `env=` in its kwargs or the dispatcher's keyword call will `TypeError`. Task 3 Step 3.7 enumerates and fixes all of them; if a plugin is missed, its `test_plugin_loads.py` or backend-call-specific test will fail loudly on the grep step.
- **UUID storage.** `EvalRun.id` is likely a `UUIDField` via `screamingface.plugins.state.base.BaseModel`. Tortoise accepts strings that parse as UUID; the test fixtures pass `str(uuid4())`. If Tortoise rejects, wrap with `uuid.UUID(...)` in the subscriber.
- **`eval-runs` doesn't depend on `python-runner`.** That's fine — the hook contract is one-way (emitters fire-and-forget). But if `python-runner` is *also* deactivated, the question hook never fires; only run-started/finished do. Document in the plugin docstring so a future debugger doesn't waste an hour.
- **Question idx counter doesn't survive restart.** If the server crashes mid-run, the `_question_idx_by_run` dict is lost; reaping orphan `running` rows + their questions is a startup-hook concern (out of scope here, separate ticket).
- **URL4 inline JSON intent.** SF-159 Task 3 found that ensemble's `split_intent` pulls `!{...}` off the top level unless wrapped in `()`. The Task 6 e2e test uses the `()`-wrapped form. If JSON with multiple keys breaks the grammar's text atom (it tolerates spaces but not commas), prefer a single-key payload in tests or URL-encode the commas.
