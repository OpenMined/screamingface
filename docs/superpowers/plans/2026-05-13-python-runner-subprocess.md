# `python_runner` subprocess runner — Implementation Plan (SF-157 / DEMO-010)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `run_script_source(source, payload, timeout) -> dict` and a structured `PythonRunnerError` to the existing `python_runner` plugin. Pure async function: source-in, payload-on-stdin, JSON-stdout-out.

**Architecture:** A single new module `runner.py` next to the existing `plugin.py`. No changes to plugin wiring or settings — DEMO-013 will glue this into `handle_backend_call`. The runner materializes source to a content-hash-keyed cache file (atomic write, 0o600), then spawns the interpreter via asyncio subprocess, pipes JSON payload to stdin, parses JSON from stdout, captures stderr. Errors raised as `PythonRunnerError(kind=...)`.

**Tech Stack:** Python 3.12, asyncio, pytest, pytest-asyncio (already installed).

**Spec:** `docs/superpowers/specs/2026-05-13-python-runner-subprocess-design.md`
**Asana:** https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214568342345700

---

## File Structure

**Create:**

- `apps/server/src/screamingface/plugins/python_runner/runner.py` — `PythonRunnerError`, `_cache_root()`, `_cache_script()`, `run_script_source()`.
- `apps/server/src/screamingface/plugins/python_runner/tests/test_runner.py` — 11 tests covering happy path, cache reuse, distinct sources, permissions, three error kinds, and stderr logging.

**Modify:** none.

---

## Task 1: `PythonRunnerError` + `_cache_script` helper

**Files:**

- Create: `apps/server/src/screamingface/plugins/python_runner/runner.py`
- Create: `apps/server/src/screamingface/plugins/python_runner/tests/test_runner.py` (initial cache + error-shape tests)

- [ ] **Step 1: Write the failing tests**

Create `apps/server/src/screamingface/plugins/python_runner/tests/test_runner.py`:

```python
"""Tests for python_runner.runner — error type + cache helper."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from screamingface.plugins.python_runner.runner import (
    PythonRunnerError,
    _cache_script,
)


def test_error_str_includes_kind_and_message() -> None:
    err = PythonRunnerError(kind="timeout", message="boom")
    assert str(err) == "PythonRunnerError(timeout): boom"


def test_error_carries_optional_fields() -> None:
    err = PythonRunnerError(
        kind="nonzero_exit",
        message="bad",
        stdout="out",
        stderr="err",
        exit_code=7,
    )
    assert err.stdout == "out"
    assert err.stderr == "err"
    assert err.exit_code == 7


def test_cache_script_writes_and_returns_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    p = _cache_script("print(1)\n")
    assert p.parent == tmp_path
    assert p.suffix == ".py"
    assert p.read_text() == "print(1)\n"


def test_cache_script_same_source_same_path_no_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    p1 = _cache_script("print(1)\n")
    mtime1 = p1.stat().st_mtime_ns
    p2 = _cache_script("print(1)\n")
    assert p1 == p2
    assert p2.stat().st_mtime_ns == mtime1


def test_cache_script_different_sources_different_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    p1 = _cache_script("print(1)\n")
    p2 = _cache_script("print(2)\n")
    assert p1 != p2


def test_cache_dir_and_file_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_root = tmp_path / "nested" / "cache"
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(cache_root))
    p = _cache_script("print('x')\n")
    assert (cache_root.stat().st_mode & 0o777) == 0o700
    assert (p.stat().st_mode & 0o777) == 0o600
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_runner.py -v
```

Expected: `ModuleNotFoundError` for `screamingface.plugins.python_runner.runner`.

- [ ] **Step 3: Write the runner module**

See the spec for the full source: `docs/superpowers/specs/2026-05-13-python-runner-subprocess-design.md`. Implement exactly what's shown there (the `PythonRunnerError` dataclass, `_cache_root()`, `_cache_script()`, and `run_script_source()`). Path: `apps/server/src/screamingface/plugins/python_runner/runner.py`.

Key points the implementer must NOT change:
- `_cache_root()` reads `os.environ.get(...)` at call time, not at module-import time.
- `os.chmod(root, 0o700)` is called every invocation (cheap, idempotent).
- The atomic write uses `tempfile.NamedTemporaryFile(..., delete=False)` as a context manager, then `os.chmod(tmp_path, 0o600)`, then `os.rename(tmp_path, target)`.
- All `raise PythonRunnerError(...)` use `from e` to preserve the cause chain.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_runner.py -v
```

Expected: 6 passed (2 error-shape + 4 cache tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/python_runner/runner.py \
        apps/server/src/screamingface/plugins/python_runner/tests/test_runner.py
git commit -m "feat(SF-157): add PythonRunnerError + cache helper for python_runner"
```

---

## Task 2: Happy path — `run_script_source` round-trip

**Files:**

- Modify: `apps/server/src/screamingface/plugins/python_runner/tests/test_runner.py` — append tests.

- [ ] **Step 1: Append the failing tests**

Append to `test_runner.py`:

```python
import textwrap

from screamingface.plugins.python_runner.runner import run_script_source


_ECHO_SCRIPT = textwrap.dedent(
    """\
    import json, sys
    data = json.load(sys.stdin)
    print(json.dumps({"ok": True, "got": data}))
    """
)


async def test_happy_path_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    result = await run_script_source(_ECHO_SCRIPT, {"a": 1, "b": [2, 3]})
    assert result == {"ok": True, "got": {"a": 1, "b": [2, 3]}}


async def test_stderr_logged_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    script = textwrap.dedent(
        """\
        import json, sys
        print("warn:something", file=sys.stderr)
        print(json.dumps({"ok": True}))
        """
    )
    with caplog.at_level(
        logging.DEBUG, logger="screamingface.plugins.python_runner.runner"
    ):
        result = await run_script_source(script, {})
    assert result == {"ok": True}
    assert any("warn:something" in rec.message for rec in caplog.records)
```

- [ ] **Step 2: Run all runner tests**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_runner.py -v
```

Expected: 8 passed (6 from Task 1 + 2 happy-path).

Note: `asyncio_mode = "auto"` is set in `pyproject.toml`, so async tests run without per-test markers.

- [ ] **Step 3: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/python_runner/tests/test_runner.py
git commit -m "test(SF-157): happy-path + stderr-logging tests for run_script_source"
```

---

## Task 3: Error paths

**Files:**

- Modify: `apps/server/src/screamingface/plugins/python_runner/tests/test_runner.py` — append tests.

- [ ] **Step 1: Append the failing tests**

Append to `test_runner.py`:

```python
async def test_nonzero_exit_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    script = textwrap.dedent(
        """\
        import sys
        print("error happened", file=sys.stderr)
        sys.exit(1)
        """
    )
    with pytest.raises(PythonRunnerError) as ei:
        await run_script_source(script, {})
    assert ei.value.kind == "nonzero_exit"
    assert ei.value.exit_code == 1
    assert "error happened" in ei.value.stderr


async def test_invalid_output_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    script = "print('not json')\n"
    with pytest.raises(PythonRunnerError) as ei:
        await run_script_source(script, {})
    assert ei.value.kind == "invalid_output"
    assert "not json" in ei.value.stdout


async def test_timeout_raises_and_kills_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    script = textwrap.dedent(
        """\
        import time
        time.sleep(5)
        """
    )
    with pytest.raises(PythonRunnerError) as ei:
        await run_script_source(script, {}, timeout=0.5)
    assert ei.value.kind == "timeout"
```

- [ ] **Step 2: Run all runner tests**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_runner.py -v
```

Expected: 11 passed. The timeout test should complete in ~0.5s. If it hangs, the kill+wait path in the runner has a bug — investigate before patching the test.

- [ ] **Step 3: Commit**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/src/screamingface/plugins/python_runner/tests/test_runner.py
git commit -m "test(SF-157): error-path tests (nonzero, invalid_output, timeout)"
```

---

## Task 4: Lint, type-check, regression

**Files:** none.

- [ ] **Step 1: ruff check + format**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run ruff check src/screamingface/plugins/python_runner
uv run ruff format --check src/screamingface/plugins/python_runner
```

Expected: both clean. If `format --check` complains, run `uv run ruff format src/screamingface/plugins/python_runner` and re-stage.

- [ ] **Step 2: pyright**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pyright src/screamingface/plugins/python_runner
```

Expected: 0 errors.

- [ ] **Step 3: Full python_runner test suite**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest src/screamingface/plugins/python_runner/ -v
```

Expected: 11 new tests + existing DEMO-009 scaffold tests still pass.

- [ ] **Step 4: Wider regression check**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run pytest -q
```

Expected: no new failures vs. main.

- [ ] **Step 5: Commit any lint/format fixups (skip if working tree clean)**

```bash
cd /Users/sergey/work/openmind/screamingface
git add -u apps/server/src/screamingface/plugins/python_runner
git commit -m "chore(SF-157): lint and type-check cleanups"
```

---

## Final acceptance check (from the spec)

- [ ] Happy path returns parsed JSON — Task 2.
- [ ] Same source → same cache path, no rewrite — Task 1.
- [ ] Different sources → different paths — Task 1.
- [ ] nonzero_exit / invalid_output / timeout all raise `PythonRunnerError` — Task 3.
- [ ] Stderr captured on success (DEBUG log) and preserved on error — Task 2 + Task 3.
- [ ] Cache dir 0o700, files 0o600 — Task 1.
- [ ] Env var read at call time — Task 1 cache tests verify by changing `SF_PYTHON_RUNNER__CACHE_ROOT` per test.
- [ ] pyright + ruff clean — Task 4.

---

## Notes for the implementer

- `asyncio_mode = "auto"` is already in `pyproject.toml`. No `@pytest.mark.asyncio` decorator needed.
- `tempfile.NamedTemporaryFile(..., delete=False)` on macOS can trigger a `ResourceWarning` if pytest runs with `-W error`. We use it as a context manager and only rename after exit — should be safe. If warnings break the test, switch to `tempfile.mkstemp(...)` + manual write/close.
- `os.chmod(root, 0o700)` runs every call (cheap, idempotent). Don't skip it when the dir already exists — a previously-too-permissive dir would never get tightened otherwise.
- `caplog.at_level(logging.DEBUG, logger="screamingface.plugins.python_runner.runner")` is the recommended form when DEBUG and the default propagation chain might miss the record.
- The 32-char digest is intentional — keeps filenames short while staying collision-safe.
- This is a pure module — no plugin.py changes, no settings changes, no route changes. If you find yourself touching those files, you're out of scope.

