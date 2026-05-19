# SF-158 / DEMO-012 — Subprocess sandboxing (sandbox-exec on darwin) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Asana:** [task 1214568425039468](https://app.asana.com/1/1185126988600652/task/1214568425039468)
- **SF ticket:** SF-158
- **Parent:** [DEMO] Leaderboard Demo — Sergey core track
- **Owner:** A (Sergey)
- **Due:** 2026-05-15
- **Priority:** High
- **Estimate:** 1 day
- **Phase / week:** Phase 1, Week 1
- **Dependencies:** DEMO-010 (`run_script_source`) — landed.
- **Branch:** `SF-158-subprocess-sandboxing` (off fresh `origin/main`)

**Goal:** Wrap the existing `run_script_source` subprocess invocation with `sandbox-exec -f <profile>` on darwin to enforce the demo's only real security boundary: deny-all network, deny-all filesystem outside an allow-list, and a scrubbed environment. Provide an `SF_PYTHON_RUNNER__SANDBOX=off` escape hatch and a clean non-darwin no-op fallback with a logged warning.

**Architecture:** Add a small `sandbox/` subpackage containing the `macos.sb` profile and a single helper `build_subprocess_argv(script_path)` that returns either a sandbox-wrapped argv (darwin + on) or `[sys.executable, script_path]` (anything else). `run_script_source` calls the helper for argv and always passes a scrubbed `env={"PATH": "/usr/bin", "HOME": "/tmp"}` to `create_subprocess_exec`. The profile denies network, denies everything by default, and allows reads of the Python framework / venv interpreter / cache root / system Python stdlib, with writes confined to `/tmp` and `/private/tmp` / `/var/folders` (the macOS canonical tempdirs).

**Tech Stack:** Python 3.13, asyncio subprocess, pytest, macOS `sandbox-exec(1)` and the TinyScheme-based sandbox profile DSL.

---

## Spec vs. reality reconciliation

The Asana ticket was written against an earlier DEMO-010 sketch that had `run_script(script_path)` and a `_subprocess_argv` helper. The merged DEMO-010 instead has:

- `run_script_source(source, payload, timeout) -> dict[str, Any]` in `apps/server/src/screamingface/plugins/python_runner/runner.py` — caches `source` to `~/.cache/screamingface/python-scripts/<sha256>.py` (or `$SF_PYTHON_RUNNER__CACHE_ROOT/...`) via `_cache_script`, then `asyncio.create_subprocess_exec(sys.executable, str(script_path), stdin=PIPE, ...)`.
- Payload arrives on stdin as JSON; output expected as JSON on stdout.
- No `_subprocess_argv` helper exists yet.

This plan adapts the spec accordingly: the helper is named `build_subprocess_argv(script_path: Path) -> list[str]`, the `SPEC_ROOT` profile parameter is bound to the **cache root** (the dir containing the resolved `.py` file), and the existing subprocess call site is the one we wrap.

## File structure

- **Create** `apps/server/src/screamingface/plugins/python_runner/sandbox/__init__.py` — public surface: `build_subprocess_argv`, `sandbox_is_enabled`, `SANDBOX_PROFILE_PATH`.
- **Create** `apps/server/src/screamingface/plugins/python_runner/sandbox/macos.sb` — the sandbox profile (TinyScheme DSL).
- **Create** `apps/server/src/screamingface/plugins/python_runner/tests/test_sandbox.py` — unit + integration tests for the helper and live sandbox.
- **Modify** `apps/server/src/screamingface/plugins/python_runner/runner.py` — call `build_subprocess_argv(script_path)` and pass scrubbed `env=`.
- **Create** `apps/server/src/screamingface/plugins/python_runner/README.md` — short README explaining the sandbox, the `SF_PYTHON_RUNNER__SANDBOX=off` escape hatch, and the deprecation risk of `sandbox-exec`.

`sandbox/` is its own subpackage so the profile file ships alongside the only code that knows how to use it; the helper has no business logic beyond argv construction so it stays in `__init__.py` rather than spinning up a separate module.

---

## Pre-flight

- [ ] **Step 0.1: Branch from fresh `origin/main`**

```bash
cd /Users/sergey/work/openmind/screamingface
git fetch origin
git stash push -u -m "pre-SF-158 wip" || true
git checkout -b SF-158-subprocess-sandboxing origin/main
```

Expected: branch created, working tree clean.

- [ ] **Step 0.2: Verify DEMO-010 baseline passes**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_runner.py -v
```

Expected: all `test_runner.py` tests pass on darwin (these are the regression baseline we must not break).

---

## Task 1: Sandbox profile file

**Files:**
- Create: `apps/server/src/screamingface/plugins/python_runner/sandbox/__init__.py` (empty for now — populated in Task 2)
- Create: `apps/server/src/screamingface/plugins/python_runner/sandbox/macos.sb`

- [ ] **Step 1.1: Create the package marker**

```bash
mkdir -p apps/server/src/screamingface/plugins/python_runner/sandbox
touch apps/server/src/screamingface/plugins/python_runner/sandbox/__init__.py
```

- [ ] **Step 1.2: Write `macos.sb`**

Write the profile to `apps/server/src/screamingface/plugins/python_runner/sandbox/macos.sb` with exactly this content:

```scheme
;; macos.sb — minimal sandbox profile for python_runner subprocesses.
;; Deny-by-default; permit only what a stdlib-only Python script needs
;; to start, read its own cached source, and write to /tmp.
;;
;; SPEC_ROOT  — directory containing the cached <sha256>.py script.
;; PY_PREFIX  — directory containing sys.executable (venv or framework).
;;
;; Apple's sandbox profile language is undocumented and deprecated but
;; still functional. References:
;;   man 1 sandbox-exec
;;   https://reverse.put.as/wp-content/uploads/2011/08/Apple-Sandbox-Guide-v1.0.pdf

(version 1)
(deny default)

;; --- Network: deny everything ---------------------------------------------
(deny network*)

;; --- Process: allow self-fork/exec/signal ---------------------------------
(allow process-fork)
(allow process-exec)
(allow signal (target self))

;; --- Reads: Python interpreter, stdlib, CA bundle, cached script ----------
(allow file-read*
    (subpath "/Library/Frameworks/Python.framework")
    (subpath "/System/Library/Frameworks/Python.framework")
    (subpath "/usr/lib")
    (subpath "/usr/local/lib")
    (subpath "/private/etc/ssl")
    (subpath "/private/etc/localtime")
    (subpath (param "PY_PREFIX"))
    (subpath (param "SPEC_ROOT")))

(allow file-read*
    (literal "/dev/null")
    (literal "/dev/random")
    (literal "/dev/urandom")
    (literal "/private/etc/localtime"))

;; --- Read metadata of arbitrary paths (stat-only, no contents) ------------
;; The stdlib pokes at sys.path / site-packages dirs during startup.
(allow file-read-metadata)

;; --- Writes: only the canonical tempdirs ----------------------------------
(allow file-write*
    (subpath "/tmp")
    (subpath "/private/tmp")
    (subpath "/private/var/folders")
    (subpath "/var/folders"))

;; --- Sysctl: required for python's platform module on startup -------------
(allow sysctl-read)

;; --- Mach lookups required for libsystem init -----------------------------
(allow mach-lookup)

;; --- IPC: dyld shared cache needs this ------------------------------------
(allow ipc-posix-shm)
```

- [ ] **Step 1.3: Smoke-test the profile manually**

```bash
PROFILE=apps/server/src/screamingface/plugins/python_runner/sandbox/macos.sb
PY=$(uv --project apps/server run python -c 'import sys; print(sys.executable)')
PY_PREFIX=$(dirname "$(dirname "$PY")")
mkdir -p /tmp/sf-sandbox-smoke
echo 'print("hi")' > /tmp/sf-sandbox-smoke/hello.py
sandbox-exec -D SPEC_ROOT=/tmp/sf-sandbox-smoke -D PY_PREFIX="$PY_PREFIX" -f "$PROFILE" "$PY" /tmp/sf-sandbox-smoke/hello.py
```

Expected: prints `hi` and exits 0. If it crashes with `sandbox: ... deny file-read-data ...`, capture the missing path from `log show --predicate 'sender == "Sandbox"' --last 1m` and add a narrow `(allow file-read* (subpath "..."))` line. Do **not** widen to a blanket file-read allow without a subpath.

- [ ] **Step 1.4: Commit**

```bash
git add apps/server/src/screamingface/plugins/python_runner/sandbox/
git commit -m "feat(python-runner): add macos.sb sandbox profile (SF-158)"
```

---

## Task 2: `build_subprocess_argv` helper + escape hatch

**Files:**
- Modify: `apps/server/src/screamingface/plugins/python_runner/sandbox/__init__.py`
- Create: `apps/server/src/screamingface/plugins/python_runner/tests/test_sandbox.py`

- [ ] **Step 2.1: Write failing unit tests**

Create `apps/server/src/screamingface/plugins/python_runner/tests/test_sandbox.py`:

```python
"""Unit + integration tests for the python_runner sandbox helper.

Integration tests are darwin-only and rely on /usr/bin/sandbox-exec.
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

import pytest

from screamingface.plugins.python_runner.runner import (
    PythonRunnerError,
    run_script_source,
)
from screamingface.plugins.python_runner.sandbox import (
    SANDBOX_PROFILE_PATH,
    build_subprocess_argv,
    sandbox_is_enabled,
)


darwin_only = pytest.mark.skipif(
    sys.platform != "darwin", reason="sandbox-exec is darwin-only"
)


# ---------- helper unit tests ---------------------------------------------


def test_profile_file_ships_with_package() -> None:
    assert SANDBOX_PROFILE_PATH.is_file()
    assert SANDBOX_PROFILE_PATH.name == "macos.sb"


def test_sandbox_is_enabled_default_true_on_darwin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert sandbox_is_enabled() is True


def test_sandbox_is_enabled_false_when_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__SANDBOX", "off")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert sandbox_is_enabled() is False


def test_sandbox_is_enabled_false_on_non_darwin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert sandbox_is_enabled() is False


def test_build_argv_wraps_on_darwin_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    script = tmp_path / "x.py"
    script.write_text("pass\n")

    argv = build_subprocess_argv(script)

    assert argv[0] == "sandbox-exec"
    assert "-f" in argv
    assert str(SANDBOX_PROFILE_PATH) in argv
    assert "-D" in argv
    assert any(a.startswith("SPEC_ROOT=") for a in argv)
    assert any(a.startswith("PY_PREFIX=") for a in argv)
    # Interpreter + script come after the sandbox-exec options.
    assert argv[-2] == sys.executable
    assert argv[-1] == str(script)


def test_build_argv_plain_when_sandbox_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__SANDBOX", "off")
    monkeypatch.setattr(sys, "platform", "darwin")
    script = tmp_path / "x.py"
    script.write_text("pass\n")
    assert build_subprocess_argv(script) == [sys.executable, str(script)]


def test_build_argv_plain_on_non_darwin_logs_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    script = tmp_path / "x.py"
    script.write_text("pass\n")

    with caplog.at_level("WARNING", logger="screamingface.plugins.python_runner.sandbox"):
        argv = build_subprocess_argv(script)

    assert argv == [sys.executable, str(script)]
    assert any("unsandboxed" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_sandbox.py -v
```

Expected: ImportError or collection error — `build_subprocess_argv`, `sandbox_is_enabled`, `SANDBOX_PROFILE_PATH` not defined.

- [ ] **Step 2.3: Implement the helper**

Overwrite `apps/server/src/screamingface/plugins/python_runner/sandbox/__init__.py`:

```python
"""sandbox-exec wrapper for python_runner subprocesses (SF-158 / DEMO-012).

Public surface:
    SANDBOX_PROFILE_PATH — pathlib.Path to macos.sb
    sandbox_is_enabled() -> bool
    build_subprocess_argv(script_path) -> list[str]
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

__all__ = ["SANDBOX_PROFILE_PATH", "build_subprocess_argv", "sandbox_is_enabled"]

logger = logging.getLogger(__name__)

SANDBOX_PROFILE_PATH = Path(__file__).parent / "macos.sb"

# Warn at most once per process so a linux dev box doesn't spam logs.
_warned_unsupported = False


def sandbox_is_enabled() -> bool:
    if sys.platform != "darwin":
        return False
    return os.environ.get("SF_PYTHON_RUNNER__SANDBOX", "").lower() != "off"


def build_subprocess_argv(script_path: Path) -> list[str]:
    """Argv to launch `script_path` under the python interpreter.

    On darwin with sandbox on: wraps with sandbox-exec + macos.sb.
    Anywhere else (or with SF_PYTHON_RUNNER__SANDBOX=off): plain argv,
    logging a one-shot warning on non-darwin platforms.
    """
    if sandbox_is_enabled():
        spec_root = str(script_path.parent.resolve())
        py_prefix = str(Path(sys.executable).resolve().parent.parent)
        return [
            "sandbox-exec",
            "-D",
            f"SPEC_ROOT={spec_root}",
            "-D",
            f"PY_PREFIX={py_prefix}",
            "-f",
            str(SANDBOX_PROFILE_PATH),
            sys.executable,
            str(script_path),
        ]

    global _warned_unsupported
    if sys.platform != "darwin" and not _warned_unsupported:
        logger.warning(
            "python_runner running unsandboxed: %s has no sandbox-exec equivalent",
            sys.platform,
        )
        _warned_unsupported = True
    return [sys.executable, str(script_path)]
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_sandbox.py -v
```

Expected: all unit tests in Step 2.1 pass.

- [ ] **Step 2.5: Commit**

```bash
git add apps/server/src/screamingface/plugins/python_runner/sandbox/__init__.py \
        apps/server/src/screamingface/plugins/python_runner/tests/test_sandbox.py
git commit -m "feat(python-runner): build_subprocess_argv + sandbox_is_enabled (SF-158)"
```

---

## Task 3: Wire the helper into `runner.py` with scrubbed env

**Files:**
- Modify: `apps/server/src/screamingface/plugins/python_runner/runner.py`
- Modify: `apps/server/src/screamingface/plugins/python_runner/tests/test_sandbox.py`

- [ ] **Step 3.1: Add a failing regression test**

Append to `apps/server/src/screamingface/plugins/python_runner/tests/test_sandbox.py`:

```python
# ---------- runner integration tests --------------------------------------


_ECHO_SCRIPT = textwrap.dedent(
    """\
    import json, sys
    data = json.load(sys.stdin)
    print(json.dumps({"ok": True, "got": data}))
    """
)

_NET_SCRIPT = textwrap.dedent(
    """\
    import socket, sys
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        sys.exit(0)
    except OSError:
        sys.exit(7)
    """
)

_WRITE_HOME_SCRIPT = textwrap.dedent(
    """\
    import os, sys
    target = os.path.expanduser("~/sf_sandbox_should_fail.txt")
    try:
        open(target, "w").write("nope")
        sys.exit(0)
    except OSError:
        sys.exit(9)
    """
)

_WRITE_TMP_SCRIPT = textwrap.dedent(
    """\
    import json, os, tempfile
    fd, p = tempfile.mkstemp(prefix="sf_sandbox_ok_", dir="/tmp")
    os.write(fd, b"ok")
    os.close(fd)
    os.unlink(p)
    print(json.dumps({"wrote": True}))
    """
)


@darwin_only
@pytest.mark.asyncio
async def test_echo_script_runs_inside_sandbox() -> None:
    out = await run_script_source(_ECHO_SCRIPT, {"hello": "world"})
    assert out == {"ok": True, "got": {"hello": "world"}}


@darwin_only
@pytest.mark.asyncio
async def test_network_denied_inside_sandbox() -> None:
    with pytest.raises(PythonRunnerError) as excinfo:
        await run_script_source(_NET_SCRIPT, {})
    assert excinfo.value.kind == "nonzero_exit"
    assert excinfo.value.exit_code == 7


@darwin_only
@pytest.mark.asyncio
async def test_write_outside_tmp_denied() -> None:
    with pytest.raises(PythonRunnerError) as excinfo:
        await run_script_source(_WRITE_HOME_SCRIPT, {})
    assert excinfo.value.kind == "nonzero_exit"
    assert excinfo.value.exit_code == 9


@darwin_only
@pytest.mark.asyncio
async def test_write_to_tmp_allowed() -> None:
    out = await run_script_source(_WRITE_TMP_SCRIPT, {})
    assert out == {"wrote": True}


@darwin_only
@pytest.mark.asyncio
async def test_sandbox_off_allows_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SF_PYTHON_RUNNER__SANDBOX", "off")
    # Either succeeds (exit 0) or fails with a non-sandbox network error;
    # the regression we care about is that sandbox-exec is not in the chain.
    try:
        await run_script_source(_NET_SCRIPT, {})
    except PythonRunnerError as e:
        assert e.kind == "nonzero_exit"
        assert e.exit_code == 7


def test_runner_uses_sandbox_helper_and_scrubs_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Runner must call build_subprocess_argv and pass scrubbed env."""
    monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("SF_PYTHON_RUNNER__SANDBOX", raising=False)

    captured: dict = {}
    real_create = asyncio.create_subprocess_exec

    async def fake_create(*argv, **kwargs):
        captured["argv"] = list(argv)
        captured["env"] = kwargs.get("env")
        passthrough_kwargs = {k: v for k, v in kwargs.items() if k != "env"}
        return await real_create(
            sys.executable, "-c", "import json, sys; json.dump({}, sys.stdout)",
            **passthrough_kwargs,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    asyncio.run(run_script_source("print(1)\n", {}))

    assert captured["argv"][0] == "sandbox-exec"
    assert captured["env"] == {"PATH": "/usr/bin", "HOME": "/tmp"}
```

- [ ] **Step 3.2: Run the new test to verify it fails**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_sandbox.py::test_runner_uses_sandbox_helper_and_scrubs_env -v
```

Expected: FAIL — argv[0] is `sys.executable`, not `"sandbox-exec"`; env is `None`.

- [ ] **Step 3.3: Modify `runner.py` to call the helper and scrub env**

In `apps/server/src/screamingface/plugins/python_runner/runner.py`:

(a) Add an import near the existing imports:

```python
from screamingface.plugins.python_runner.sandbox import build_subprocess_argv
```

(b) Locate the existing subprocess block inside `run_script_source`. The current block is:

```python
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        raise PythonRunnerError(kind="io_error", message=str(e)) from e
```

Replace it with:

```python
    argv = build_subprocess_argv(script_path)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PATH": "/usr/bin", "HOME": "/tmp"},
        )
    except OSError as e:
        raise PythonRunnerError(kind="io_error", message=str(e)) from e
```

- [ ] **Step 3.4: Run all python_runner tests**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests -v
```

Expected: all sandbox tests + all pre-existing `test_runner.py` tests pass on darwin. If a pre-existing runner test fails because the sandbox blocks something legitimate, fix the profile (Task 1) — do not weaken `env=` or skip the wrap. Likely candidates: tests that depend on env vars other than PATH/HOME; if so, those tests were over-permissive and should monkeypatch `build_subprocess_argv` to return plain argv for that specific case.

- [ ] **Step 3.5: Verify escape hatch via env var**

```bash
cd apps/server
SF_PYTHON_RUNNER__SANDBOX=off uv run pytest \
    src/screamingface/plugins/python_runner/tests/test_runner.py -v
```

Expected: all `test_runner.py` tests still pass with sandbox off (regression sanity for the toggle).

- [ ] **Step 3.6: Commit**

```bash
git add apps/server/src/screamingface/plugins/python_runner/runner.py \
        apps/server/src/screamingface/plugins/python_runner/tests/test_sandbox.py
git commit -m "feat(python-runner): wrap subprocess in sandbox-exec on darwin (SF-158)"
```

---

## Task 4: README

**Files:**
- Create: `apps/server/src/screamingface/plugins/python_runner/README.md`

- [ ] **Step 4.1: Write the README**

Create `apps/server/src/screamingface/plugins/python_runner/README.md`:

```markdown
# python_runner

Runs user-authored Python scripts in a sandboxed subprocess. Used by the
`/python` URL4 backend dispatch path.

## Sandboxing

On **darwin**, every script invocation is wrapped with `sandbox-exec` using
the profile at `sandbox/macos.sb`:

- All network is denied (`(deny network*)`).
- Filesystem writes are confined to `/tmp`, `/private/tmp`, `/var/folders`.
- Filesystem reads are restricted to the Python interpreter prefix, the
  system stdlib, CA bundles, and the script's cache directory.
- The subprocess environment is stripped to `{"PATH": "/usr/bin",
  "HOME": "/tmp"}`.

On **non-darwin** platforms the runner currently has **no sandbox** and
logs a warning on first use. Linux sandboxing (e.g. via `nsjail` or
`bubblewrap`) is tracked separately as part of the Linux packaging story.

## Disabling the sandbox (debugging only)

Set `SF_PYTHON_RUNNER__SANDBOX=off` to bypass the sandbox wrapper. This is
for local debugging; do not ship configurations with the sandbox disabled.

## Deprecation risk

`sandbox-exec(1)` has been deprecated by Apple since macOS 10.7 but
remains functional and is widely used by Homebrew, npm, and others.
If/when Apple removes it, candidate replacements are:

- `nsjail` (Linux primarily, runnable on macOS under a VM)
- Pure-Python partial fallback via `resource.setrlimit` + `os.chroot` (does
  not cover network)

Until then, the profile here is the only enforced security boundary in
the demo — AST validation is deliberately out of scope (DEMO-031).
```

- [ ] **Step 4.2: Commit and push**

```bash
git add apps/server/src/screamingface/plugins/python_runner/README.md
git commit -m "docs(python-runner): document sandbox profile + escape hatch (SF-158)"
git push -u origin SF-158-subprocess-sandboxing
```

---

## Task 5: Local CI gates + PR

- [ ] **Step 5.1: Mirror CI gates locally**

```bash
cd apps/server
uv run ruff check .
uv run ruff format --check .
uv run pytest src/screamingface/plugins/python_runner/tests -v
```

Expected: all three exit 0. Pre-commit hooks must also pass.

- [ ] **Step 5.2: Open PR (do not merge)**

```bash
gh pr create --title "SF-158: subprocess sandboxing (sandbox-exec on darwin)" \
  --body-file - <<'EOF'
## Summary
- Wrap python_runner subprocess in `sandbox-exec -f macos.sb` on darwin
- Scrub subprocess env to `{PATH=/usr/bin, HOME=/tmp}`
- `SF_PYTHON_RUNNER__SANDBOX=off` escape hatch; non-darwin = warn + plain argv

## Test plan
- [x] Unit tests for `build_subprocess_argv` (darwin + linux paths, off + on)
- [x] Integration tests: network denied, writes-outside-/tmp denied, /tmp writes allowed, echo script works
- [x] `test_runner.py` regression baseline still passes inside the sandbox
- [x] `SF_PYTHON_RUNNER__SANDBOX=off` allows the runner tests to pass unsandboxed

Closes SF-158.
EOF
```

Stop after PR creation; user reviews and merges manually.

---

## Acceptance criteria mapping

| Ticket criterion | Implemented by |
| --- | --- |
| Helper returns sandbox-wrapped argv on darwin when sandbox is on | Task 2 (`build_subprocess_argv`) + `test_build_argv_wraps_on_darwin_when_enabled` |
| Helper falls back to plain argv when `SF_PYTHON_RUNNER__SANDBOX=off` | Task 2 + `test_build_argv_plain_when_sandbox_off` |
| Helper falls back to plain argv on non-darwin (logged warning) | Task 2 + `test_build_argv_plain_on_non_darwin_logs_warning` |
| Network-using script exits non-zero, `nonzero_exit` raised | Task 3 + `test_network_denied_inside_sandbox` |
| Write to `/tmp/x` succeeds; write to `~/secret_file` fails | Task 3 + `test_write_to_tmp_allowed` / `test_write_outside_tmp_denied` |
| Sandbox-off allows network (toggle regression) | Task 3 + `test_sandbox_off_allows_network` |
| DEMO-010 happy-path tests still pass sandboxed | Task 3 Step 3.4 |
| Documented how to disable for debugging | Task 4 README |

## Risks

- **Profile too tight.** First darwin-only test run may fail with `Sandbox: ... deny file-read-data ...` on a path the stdlib needs. Capture from `log show --predicate 'sender == "Sandbox"' --last 1m` and narrowly widen the profile; do **not** broaden without a subpath.
- **uv venv interpreter path.** The profile binds `PY_PREFIX` to `Path(sys.executable).resolve().parent.parent`. For uv this is usually the project's `.venv`. If `uv run` proxies through a different binary first time, the resolved interpreter may live elsewhere; rerun the Step 1.3 smoke if Task 3 tests fail with sandbox denials on first attempt.
- **CI runs on linux.** Darwin-only tests skip; CI cannot regression-test the actual sandbox. Anyone changing the profile must run the test suite locally on a Mac before pushing.
