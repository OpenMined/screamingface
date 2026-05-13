---
title: python_runner — subprocess runner + JSON I/O contract
status: proposed
asana_task: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214568342345700
asana_gid: 1214568342345700
sf_id: SF-157
depends_on: DEMO-009 (python_runner scaffold) — merged
blocks: DEMO-012 (sandbox-exec wrap), DEMO-013 (/python route wiring)
created: 2026-05-13
---

# `python_runner` — subprocess runner + JSON I/O contract

## Goal

Add `run_script_source(source, payload, timeout) -> dict` to the existing
`python_runner` plugin. Pure async function: Python source string in, JSON
payload to stdin, parsed JSON stdout out. Errors raised as a structured
`PythonRunnerError`. No path arguments — the caller is responsible for
producing the source from wherever it lives.

This is the **execution primitive**. Sandboxing wraps it transparently in
DEMO-012; the `/python` URL4 backend route wires source-fetching +
execution in DEMO-013.

## Background

DEMO-009 landed the plugin scaffold: `PythonRunnerPlugin`,
`PythonRunnerSettings` (which holds `scripts: dict[str, str]` —
config-stored script library, a separate concern from execution),
`routes.py` stub, and the `_vendored/` directory for bundled HLE scripts.
The scaffold's `handle_backend_call` is a `NotImplementedError` stub until
DEMO-013. This ticket fills in the underlying primitive DEMO-013 will call.

## Scope

In:
- New module `apps/server/src/screamingface/plugins/python_runner/runner.py`
- Public coroutine `run_script_source(source, payload, timeout=30.0) -> dict`
- Structured exception `PythonRunnerError`
- Internal helper `_cache_script(source) -> Path` with content-hash-keyed
  atomic writes, 0o700 dir / 0o600 file
- Tests: happy path, cache reuse, error paths, stderr capture, permissions

Out:
- Sandbox profile (DEMO-012)
- Wiring to `/python` route (DEMO-013)
- Per-call cache invalidation / size limits / LRU eviction
- Process pool / warm interpreters
- Modifying `plugin.py`, `routes.py`, `PythonRunnerSettings`

## Design

### Architecture

A single module, two public names (`run_script_source`,
`PythonRunnerError`) and one private helper (`_cache_script`). No FastAPI
integration, no class hierarchy — just an async function. DEMO-013
imports and awaits it from the plugin's `handle_backend_call`.

### `PythonRunnerError`

```python
ErrorKind = Literal["nonzero_exit", "invalid_output", "timeout", "io_error"]


@dataclass
class PythonRunnerError(Exception):
    kind: ErrorKind
    message: str
    stderr: str = ""
    stdout: str = ""
    exit_code: int | None = None

    def __str__(self) -> str:
        return f"PythonRunnerError({self.kind}): {self.message}"
```

`@dataclass` on an Exception subclass generates `__init__` and `__repr__`;
`__str__` is explicit so log lines stay readable. All raise sites use
`raise ... from e` to preserve the cause chain.

### `_cache_script`

```python
_DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "screamingface" / "python-scripts"


def _cache_root() -> Path:
    return Path(os.environ.get("SF_PYTHON_RUNNER__CACHE_ROOT", _DEFAULT_CACHE_ROOT))


def _cache_script(source: str) -> Path:
    root = _cache_root()
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]
    target = root / f"{digest}.py"
    if target.exists():
        return target
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    with tempfile.NamedTemporaryFile(
        "w", dir=root, suffix=".py.tmp", delete=False
    ) as tmp:
        tmp.write(source)
        tmp_path = tmp.name
    os.chmod(tmp_path, 0o600)
    os.rename(tmp_path, target)
    return target
```

> **Why read the env var at call time, not module top.** Pytest's
> `monkeypatch.setenv` sets the env var before each test. If we cached the
> resolved path at module-import time the first test would freeze the
> value. Reading inside `_cache_root()` makes the function tractable from
> tests at essentially zero runtime cost.

> **Why 32-hex-char digest.** sha256 hex is 64 chars; 32 is enough
> collision resistance for a content-addressed cache (~2^128) and keeps
> the filename short.

> **Atomic write via tmp + rename.** Same digest may be written
> concurrently by two coroutines. Both write their own tmp file and both
> rename to the same target — POSIX rename is atomic, and since the
> content is identical (same digest), the result is the same regardless
> of which rename wins.

### `run_script_source`

```python
logger = logging.getLogger(__name__)


async def run_script_source(
    source: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    script_path = _cache_script(source)
    payload_bytes = json.dumps(payload).encode("utf-8")

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

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=payload_bytes),
            timeout=timeout,
        )
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise PythonRunnerError(
            kind="timeout",
            message=f"Script exceeded {timeout}s timeout",
        ) from e

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    exit_code = proc.returncode

    if exit_code != 0:
        raise PythonRunnerError(
            kind="nonzero_exit",
            message=f"Script exited with code {exit_code}",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )

    if stderr:
        logger.debug("python_runner stderr (non-empty on success): %s", stderr)

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise PythonRunnerError(
            kind="invalid_output",
            message=f"Stdout is not valid JSON: {e}",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        ) from e
```

### I/O contract for scripts

Scripts read JSON from stdin, parse it, write JSON to stdout. Anything to
stderr is treated as logs (captured but not parsed). A minimal valid
script:

```python
# example.py
import json, sys
data = json.load(sys.stdin)
print(json.dumps({"ok": True, "got": data}))
```

`run_script_source(open("example.py").read(), {"a": 1})` returns
`{"ok": True, "got": {"a": 1}}`.

## Error Handling

| Condition | Behaviour |
| --- | --- |
| Cannot spawn interpreter (e.g. `sys.executable` missing) | `PythonRunnerError(kind="io_error")` |
| Script exceeds `timeout` | kill + wait; `PythonRunnerError(kind="timeout")` |
| Script exits non-zero | `PythonRunnerError(kind="nonzero_exit", exit_code=...)`, stdout/stderr populated |
| Script exits 0 but stdout isn't JSON | `PythonRunnerError(kind="invalid_output")`, stdout/stderr populated |
| Script exits 0 with empty stderr | Return parsed dict |
| Script exits 0 with non-empty stderr | `logger.debug(...)`, return parsed dict |
| Concurrent identical writes to cache | Both rename atomically to same path; safe |

## Testing

All tests use `tmp_path` +
`monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", str(tmp_path))`.

- **`test_happy_path`** — inline 4-line script reads stdin, returns dict.
- **`test_cache_reuse_same_source`** — capture mtime of cached file; call
  again with same source; assert mtime unchanged AND path identical.
- **`test_different_sources_different_paths`** — two slightly different
  sources produce two cache files.
- **`test_cache_dir_permissions`** — assert `Path.stat().st_mode & 0o777`
  equals `0o700` on the dir and `0o600` on the file.
- **`test_nonzero_exit_raises`** — `sys.exit(1)` script; assert
  `PythonRunnerError(kind="nonzero_exit", exit_code=1)` with non-empty
  stderr.
- **`test_invalid_output_raises`** — script prints `"not json"`; assert
  `kind="invalid_output"`.
- **`test_timeout_raises`** — script sleeps 5s, timeout=0.5; assert
  `kind="timeout"`; assert the proc is killed (no leftover).
- **`test_stderr_logged_on_success`** — script writes to stderr then valid
  JSON to stdout; with `caplog.at_level(logging.DEBUG)`, assert log
  contains the stderr text.

```
cd apps/server
uv run pytest src/screamingface/plugins/python_runner/tests/test_runner.py -v
```

Expected: 8 tests green, <10s.

## Acceptance Criteria

- [ ] `run_script_source(source, payload)` returns parsed JSON on happy path.
- [ ] Same source → same cache path; mtime unchanged on repeat call.
- [ ] Different sources → different cache paths.
- [ ] `nonzero_exit` / `invalid_output` / `timeout` paths all raise
      `PythonRunnerError` with the right `kind`.
- [ ] Stderr captured on success (logged at DEBUG when non-empty);
      preserved on error (in `PythonRunnerError.stderr`).
- [ ] Cache dir is `0o700`; cache files are `0o600`.
- [ ] `monkeypatch.setenv("SF_PYTHON_RUNNER__CACHE_ROOT", ...)` redirects
      cache for tests (env var read at call time, not at import time).
- [ ] pyright + ruff clean.

## Out of scope

- DEMO-012 sandbox wrapping (allow-lists `_cache_root()` for read+exec).
- DEMO-013 `/python` route wiring (source fetch + dispatch to this runner).
- Cache size bounds / eviction.
- Worker / interpreter pool.

## Follow-ups

- DEMO-012 wraps `asyncio.create_subprocess_exec` with the macOS
  sandbox-exec profile so reads + executions are only allowed under
  `_cache_root()`, and network is denied.
- DEMO-013 wires `handle_backend_call` in `plugin.py` to fetch source
  from the URL, then call `run_script_source`.
