# url4 packed_context blob dereference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dereference `/data/<blob-key>` references that appear inside a url4 backend call's `packed_context` (the text in `/claude(...)`), so a `$prompt`-substituted blob is fetched to its stored content before the backend/LLM sees it — instead of leaking the literal path string.

**Architecture:** A url4 backend call `/path(packed_context)!intent` resolves its `intent` through the AST tree (`resolve()` → `Url4RelUrl` → `_fetch_relative`) but passes `packed_context` to the plugin **verbatim**. We close that asymmetry for the one case that needs it — blob-store references — by token-scanning `packed_context` for `/data/<16-hex-key>` and replacing each with its fetched body, reusing the existing in-process `_fetch_relative`. Author-written script paths like `/python(/data/code/agg.py)` are deliberately left untouched.

**Tech Stack:** Python 3.12, FastAPI, pytest (`pytest-asyncio`), ruff 0.9.0 (pinned in pre-commit), pyright. Server lives in `apps/server`.

---

## Background — root cause (verified)

The active spec in `apps/server/sf.json` is `(claude:0.40:/claude($prompt)!'…', …)!'…'`. The frontend substitutes `$prompt` → `/data/<key>` **before** the executor runs (memory: `$prompt`/`$reducer` are frontend-only reserved vars), producing `/claude(/data/<key>)!'…'`. That parses to `Url4BackendCall(packed_context='/data/<key>', intent=Url4Text('…'))`.

In `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`:
- **line 148** `intent_text = … await resolve(node.intent, app, env)` — the intent **is** resolved (a `/data/...` intent would be fetched via `Url4RelUrl` → `_fetch_relative`).
- **line 150** `sources_text = node.packed_context or ""` — `packed_context` is taken **raw** and handed to the plugin at **lines 161–162** `plugin.handle_backend_call(intent_text, sources=sources_text, …)`. The blob is never fetched; the literal `/data/<key>` reaches the LLM.

This is **not** the "unshared blob_store across the proxy/backend HTTP split" theory — the leak reproduces even on the in-process path (the desktop-dev default). It is purely the **intent-vs-packed_context asymmetry**.

### The discriminator (why a naive fix breaks production)

Two different `/data/...` shapes flow through `packed_context`:

| Form | Example | Origin | Must be |
|------|---------|--------|---------|
| **Blob ref** | `/data/a1b2c3d4e5f6a7b8` | `$prompt` substitution; key = `sha256(data).hexdigest()[:16]` (`data_store/storage.py:36`) — **16 lowercase hex, single segment** | **Dereferenced** to content |
| **Script path** | `/data/code/agg.py` | author-written reducer arg to `/python(...)` | **Left literal** |

The `/python` script-path contract is **asserted by existing passing tests** and must not regress:
- `url4_executor/tests/test_collection_reducer.py:59` → `assert py.calls[-1][1] == "/data/code/agg.py"`
- `test_env_vars.py:63`, `test_json_blob.py:6,14`, `test_run_headers.py:116` all use `/python(/data/code/x.py)`.

The two are cleanly separable by shape: a blob ref is `/data/` + exactly 16 hex chars, delimiter-bounded; `/data/code/...` is multi-segment and `code` is not 16 hex. So the fix matches **only** `/data/[0-9a-f]{16}` (bounded) and ignores everything else.

## File structure

- **Modify:** `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`
  - add `import re`
  - add helper `_resolve_blob_refs(text, app)`
  - change line 150 to call it
- **Create:** `apps/server/src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py`

Scope is one production file + one test file. No frontend change — all **four** frontend services emit the bare `/data/<key>` token this fix now resolves, at their substitution sites (`claude_frontend/_url4_context.py:228`, `codex_frontend/proxy.py:259`, `gemini_frontend/proxy.py:213`, `ollama_frontend/proxy.py:196-197`). The fix lives in the shared `url4_executor`, so it covers all four uniformly regardless of which frontend produced the ref.

> **Run commands** (from repo root): tests `cd apps/server && uv run pytest -q <path>`; types `cd apps/server && uv run pyright`; pre-commit `pre-commit run --files <changed files>` (ruff 0.9.0 — if `ruff-format` reformats, re-stage and re-run).

---

### Task 1: Failing test — blob ref in packed_context is dereferenced

**Files:**
- Create: `apps/server/src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py`

- [ ] **Step 1: Write the failing test**

```python
"""packed_context blob dereference (the $prompt-in-parens leak).

A `/data/<16-hex>` blob ref inside `/claude(...)` parens must be fetched to its
stored body before the plugin sees it, while `/python(/data/code/x.py)` script
paths stay literal.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from screamingface.plugins.url4_executor.url4 import resolve_str
from screamingface.plugins.url4_executor.tests.test_ensemble import (
    _FakeDispatchPlugin,
    _make_app,
)

_FETCH_REL = "screamingface.plugins.url4_executor.url4_resolve._fetch_relative"
_BLOB_KEY = "a1b2c3d4e5f6a7b8"  # 16 lowercase hex == sha256(data)[:16] shape


@pytest.mark.asyncio
async def test_blob_ref_in_packed_context_is_dereferenced():
    py = _FakeDispatchPlugin(name="claude", paths=["/claude"], responses=["ok"])
    app = _make_app(py)
    with patch(_FETCH_REL, new_callable=AsyncMock, return_value="USER PROMPT BODY") as fetch:
        await resolve_str(f"/claude(/data/{_BLOB_KEY})!summarize", app)
    fetch.assert_awaited_once_with(app, f"/data/{_BLOB_KEY}")
    # calls tuple is (intent, sources, env); sources must be the fetched body
    assert py.calls[-1][1] == "USER PROMPT BODY"
    assert py.calls[-1][0] == "summarize"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py::test_blob_ref_in_packed_context_is_dereferenced -v`
Expected: FAIL — `_fetch_relative` is never awaited and `py.calls[-1][1] == "/data/a1b2c3d4e5f6a7b8"` (the literal leak), so both assertions fail.

---

### Task 2: Regression-guard test — `/python` script path stays literal

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py`

This locks the contract that the fix must NOT break. It passes both before and after the fix; if a future change over-broadens the regex, it goes red.

- [ ] **Step 1: Add the regression test**

```python
@pytest.mark.asyncio
async def test_python_script_path_is_not_dereferenced():
    py = _FakeDispatchPlugin(name="python-runner", paths=["/python"], responses=["ok"])
    app = _make_app(py)
    with patch(_FETCH_REL, new_callable=AsyncMock, return_value="SHOULD NOT BE USED") as fetch:
        await resolve_str('/python(/data/code/agg.py)!{}', app)
    fetch.assert_not_awaited()
    assert py.calls[-1][1] == "/data/code/agg.py"  # literal path preserved
```

- [ ] **Step 2: Run it (must already pass pre-fix)**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py::test_python_script_path_is_not_dereferenced -v`
Expected: PASS — current code passes `packed_context` through verbatim, so `_fetch_relative` is not called and sources is the literal path.

---

### Task 3: Implement `_resolve_blob_refs` and wire it in

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py`

- [ ] **Step 1: Add the `re` import**

At the top of the module, add `import re` alongside the existing stdlib imports (after `import logging`):

```python
import asyncio
import logging
import re
from typing import Any
```

- [ ] **Step 2: Add the helper immediately above `_dispatch_backend_call`**

Insert before `async def _dispatch_backend_call(` (currently line 133):

```python
# A data-store blob reference: ``/data/`` + a 16-char sha256 key
# (data_store/storage.py: ``sha256(data).hexdigest()[:16]``), as emitted by the
# frontend ``$prompt`` substitution (e.g. claude_frontend/_url4_context.py:228).
# Bounded so literal prose and multi-segment script paths like
# ``/data/code/agg.py`` (which /python must receive verbatim) never match.
_BLOB_REF_RE = re.compile(r"(?<![0-9A-Za-z/])/data/[0-9a-f]{16}(?![0-9A-Za-z/])")


async def _resolve_blob_refs(text: str, app: Any) -> str:
    """Dereference ``/data/<blob-key>`` refs embedded in a backend call's packed_context.

    The ``intent`` slot of a backend call is resolved through the AST tree
    (``resolve`` -> ``Url4RelUrl`` -> ``_fetch_relative``), but ``packed_context``
    is free text handed to the plugin verbatim. When the frontend substitutes a
    ``$prompt`` that sits inside the call parens (``/claude($prompt)!...``) it
    becomes a literal ``/data/<key>`` token; without this it would leak to the LLM
    as the path string instead of the stored prompt body.

    Only blob-key-shaped refs are dereferenced. Author-written script paths such
    as ``/python(/data/code/agg.py)`` — which the runner must receive as a literal
    path — do not match and pass through unchanged. Surrounding prose is preserved;
    each matched ref is replaced by its fetched body via the in-process
    ``_fetch_relative`` (which raises on a missing key — fail loud, by design).
    """
    matches = list(_BLOB_REF_RE.finditer(text))
    if not matches:
        return text
    parts: list[str] = []
    last = 0
    for m in matches:
        parts.append(text[last : m.start()])
        parts.append(await _fetch_relative(app, m.group(0)))
        last = m.end()
    parts.append(text[last:])
    return "".join(parts)
```

- [ ] **Step 3: Wire it at line 150**

Replace:

```python
    sources_text = node.packed_context or ""
```

with:

```python
    sources_text = await _resolve_blob_refs(node.packed_context or "", app)
```

- [ ] **Step 4: Run Task 1 + Task 2 tests — both pass**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py -v`
Expected: both PASS — blob ref dereferenced to `"USER PROMPT BODY"`; `/python` script path still literal and `_fetch_relative` not called for it.

---

### Task 4: Edge cases — mixed prose and fail-loud on missing key

**Files:**
- Modify: `apps/server/src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py`

- [ ] **Step 1: Add mixed-prose + multi-ref + missing-key tests**

```python
@pytest.mark.asyncio
async def test_blob_ref_mixed_with_prose_only_replaces_the_ref():
    py = _FakeDispatchPlugin(name="claude", paths=["/claude"], responses=["ok"])
    app = _make_app(py)
    with patch(_FETCH_REL, new_callable=AsyncMock, return_value="BODY"):
        await resolve_str(f"/claude(intro /data/{_BLOB_KEY} outro)!go", app)
    assert py.calls[-1][1] == "intro BODY outro"


@pytest.mark.asyncio
async def test_two_blob_refs_both_dereferenced():
    key2 = "0011223344556677"
    py = _FakeDispatchPlugin(name="claude", paths=["/claude"], responses=["ok"])
    app = _make_app(py)

    async def _fake_fetch(app_, path):
        return {f"/data/{_BLOB_KEY}": "AAA", f"/data/{key2}": "BBB"}[path]

    with patch(_FETCH_REL, new=AsyncMock(side_effect=_fake_fetch)):
        await resolve_str(f"/claude(/data/{_BLOB_KEY},/data/{key2})!go", app)
    assert py.calls[-1][1] == "AAA,BBB"


@pytest.mark.asyncio
async def test_missing_blob_key_raises_fail_loud():
    import httpx

    py = _FakeDispatchPlugin(name="claude", paths=["/claude"], responses=["ok"])
    app = _make_app(py)
    boom = httpx.HTTPStatusError("404", request=httpx.Request("GET", "http://x"), response=httpx.Response(404))
    with patch(_FETCH_REL, new=AsyncMock(side_effect=boom)):
        with pytest.raises(httpx.HTTPStatusError):
            await resolve_str(f"/claude(/data/{_BLOB_KEY})!go", app)
```

Note on the two-refs case: `/data/<k1>,/data/<k2>` — the comma sits between two backend-call-free tokens; confirm the grammar keeps this as one `packed_context` string for a single `/claude(...)` call (it is inside the parens, so commas are literal context, not list separators). If the parser instead splits it, drop this specific test and keep the single-ref + mixed-prose cases — the helper logic is identical.

- [ ] **Step 2: Run the full new test file**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py -v`
Expected: all PASS.

---

### Task 5: Full suite, types, pre-commit, commit

**Files:** none (verification)

- [ ] **Step 1: Run the whole url4_executor suite (catch regressions, esp. /python tests)**

Run: `cd apps/server && uv run pytest -q src/screamingface/plugins/url4_executor/tests/`
Expected: PASS — including `test_collection_reducer.py`, `test_env_vars.py`, `test_json_blob.py`, `test_run_headers.py` (the `/python(/data/code/*.py)` contract).

- [ ] **Step 2: Run the e2e ensemble tests that exercise dispatch end to end**

Run: `cd apps/server && uv run pytest -q tests/e2e/test_ensemble_features.py`
Expected: PASS.

- [ ] **Step 3: Types**

Run: `cd apps/server && uv run pyright src/screamingface/plugins/url4_executor/url4_resolve.py`
Expected: 0 errors. (Editor pyright squiggles without the server venv are false positives; this command is authoritative.)

- [ ] **Step 4: pre-commit on changed files (ruff 0.9.0)**

Run: `pre-commit run --files apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py apps/server/src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py`
If `ruff-format` reformats, re-stage and re-run until clean.

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/screamingface/plugins/url4_executor/url4_resolve.py \
        apps/server/src/screamingface/plugins/url4_executor/tests/test_packed_context_blob_deref.py
git commit -m "fix(url4): dereference /data/<key> blob refs in backend-call packed_context

A \$prompt substituted inside call parens (/claude(\$prompt)!...) became a
literal /data/<key> token that leaked to the LLM. packed_context now resolves
blob-key-shaped refs via _fetch_relative, mirroring the intent path, while
leaving /python(/data/code/*.py) script paths untouched."
```

---

## Self-review

**Spec coverage:** the reported leak (Task 1/3), the `/python` non-regression (Task 2, plus full-suite Task 5.1), mixed/multi refs (Task 4), and fail-loud on missing key (Task 4) are all covered.

**Discriminator safety:** `_BLOB_REF_RE` matches `/data/` + exactly 16 hex, delimiter-bounded; `/data/code/agg.py` cannot match (`code` is not 16 hex; multi-segment). In-process and HTTP both resolve through this same `_dispatch_backend_call`, so the fix is locus-uniform.

**Type consistency:** `_resolve_blob_refs(text: str, app: Any) -> str`; called exactly once at line 150; reuses existing `_fetch_relative(app, path) -> str`.

## Open questions / risks (carry to review)

1. **Intent-slot form already works.** If a spec instead writes `/claude(...)!$prompt` (`$prompt` in the *intent*), it resolves today via `resolve()` → `Url4RelUrl`. This fix is scoped to `packed_context` only and does not touch that path. The confirmed failing spec uses the parens form, so this fix targets the real bug.
2. **Non-blob backends.** The 16-hex shape means only data-store blobs are touched; no current or plausible backend passes a literal `/data/<16-hex>` it needs un-dereferenced (`/python` uses `/data/code/*.py`). If one ever does, gate dereferencing on backend semantics instead of shape.
3. **Absolute URLs in packed_context.** The intent path also fetches `http(s)://`. If specs ever embed absolute URLs as context, extend `_resolve_blob_refs` to also handle `http(s)://` tokens for symmetry — deferred; no evidence it's used.
4. **Fail-loud change.** A missing/expired key now raises (via `_fetch_relative`'s `raise_for_status`) instead of silently leaking the path. This matches the project's fail-loud direction and the frontend already renders resolution errors as a visible `[url4 error]`. Confirm no caller relies on the old silent passthrough.

## Notes
- Independent of the frontend terminal-ensemble reframing; ships on its own.
- At implementation time: branch from fresh `origin/main` as `SF-NNN-url4-packed-context-blob-deref` (create the Asana ticket first for the SF id), work in a git worktree, open a PR, do not auto-merge.
