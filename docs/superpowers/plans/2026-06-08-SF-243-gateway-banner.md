# SF-243 — claude CLI launcher banner (url4 ensemble gateway)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** When a user launches the `claude` CLI redirected to the gateway, they immediately see a banner stating they're on the ScreamingFace url4 ensemble gateway and **which active url4 spec** answers their queries (or a warning if none) — without polluting claude's stdout/protocol.

**Architecture:** `claude_env_intercept` already owns an idempotent, teardown-safe marker block in every shell rc (`.zshrc`/`.bashrc`/`.profile`…) that today holds only `export ANTHROPIC_BASE_URL=…`. We add a `claude()` **shell function** to that same block. The function prints the banner to **stderr** then runs the real binary via `command claude "$@"` (no recursion). The banner is **rendered at `setup()`** from the live plugin (`cf_settings.active_spec` + `cf_plugin.get_active_expression()`) and **baked into the function with `shlex.quote()`** — one `printf '%s\n' '<quoted line>' >&2` per banner line — so escaping is bulletproof for arbitrary url4 expressions (quotes, `$`, `(`, `)`, `!`, backticks) and there is no runtime config lookup. Teardown is automatic: `remove_exports()` strips the whole block (function included).

**Design rationale (verified):** an earlier dynamic design (a `sf claude-env-intercept banner` subcommand reading `sf.json` at launch) was rejected by adversarial review — in real interactive shells `SF_CONFIG` is unset and `load_config()` reads `./sf.json` relative to the user's cwd, so the spec resolves to *None* in almost every launch (and the `SF_CONFIG`-path fix is broken: that var carries inline JSON, not a path). Baking at setup avoids all of it. Tradeoff: the banner reflects the spec **as of intercept activation** (same lifecycle as the `ANTHROPIC_BASE_URL` export); re-activating refreshes it. The shell-safety core (no recursion, POSIX/bash/zsh-safe, stderr-only, block idempotency, teardown removal, no breakage when the gateway is inactive) was empirically confirmed in review and is unchanged here.

**Tech Stack:** Python 3.13, `shlex` (stdlib), pytest (`asyncio_mode="auto"`), pyright, ruff 0.9.0. Shell: POSIX sh (bash/zsh/dash compatible).

**Worktree / branch:** `/private/tmp/SF-243-gateway-banner` on `SF-243-gateway-banner` (cut from `origin/main` `1f1ef24`).

**Gate (run from `apps/server`):**
- Targeted: `uv run pytest -q src/screamingface/plugins/claude_env_intercept/tests/`
- Full (mirror CI): `uv run pytest -q -m "not live" tests/ src/screamingface/plugins/`
- Types: `uv run pyright` · Pre-commit (from `apps/server`): `pre-commit run --files <changed files>`

---

## File Structure

| File | Responsibility |
|---|---|
| `.../plugins/claude_env_intercept/shellenv.py` (Modify) | `add_exports` gains `extra_lines`; add `render_gateway_banner` + `build_claude_banner_function` |
| `.../plugins/claude_env_intercept/plugin.py` (Modify) | `setup()` renders the banner from `cf_plugin` and passes the function into the block |
| `.../plugins/claude_env_intercept/tests/test_claude_env.py` (Modify) | tests for render, the shell function (executed in a real shell), block write/remove, and the setup() wiring |

---

## Task 1: shellenv — banner renderer + function builder + block plumbing

**Files:** `shellenv.py`, `tests/test_claude_env.py`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_claude_env.py` (inside `class TestShellEnv`, reusing the existing `profile_file`/`_patch_profile` fixtures; add `import os`, `import subprocess`, `import shutil`, `import pytest` at top if absent):

```python
    def test_render_banner_with_spec(self) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import render_gateway_banner

        out = render_gateway_banner("my-spec", "(https://x/r.txt)!$prompt")
        assert "url4 ensemble gateway" in out
        assert "my-spec" in out
        assert "(https://x/r.txt)!$prompt" in out

    def test_render_banner_no_spec_warns(self) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import render_gateway_banner

        for name, expr in [(None, None), ("", None), ("x", None)]:
            out = render_gateway_banner(name, expr)
            assert "WARNING" in out
            assert "active url4 spec" in out

    @pytest.mark.parametrize("shell", ["sh", "bash", "zsh"])
    def test_function_prints_banner_to_stderr_and_runs_claude(self, tmp_path, shell) -> None:
        # The generated function must: print the (hostile) banner verbatim to STDERR,
        # leave STDOUT for the real binary, never recurse, and exit 0.
        from screamingface.plugins.claude_env_intercept.shellenv import (
            build_claude_banner_function,
            render_gateway_banner,
        )

        if shutil.which(shell) is None:
            pytest.skip(f"{shell} not installed")

        # Expression with every shell-hostile character.
        banner = render_gateway_banner("s p e c", "(a|b)!$prompt '\"`x` $(y) ! ()")
        func = build_claude_banner_function(banner)

        bindir = tmp_path / "bin"
        bindir.mkdir()
        fake = bindir / "claude"
        fake.write_text("#!/bin/sh\necho REAL_CLAUDE_RAN \"$@\"\n")
        fake.chmod(0o755)

        script = f"{func}\nclaude --model x\n"
        env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
        r = subprocess.run([shell, "-c", script], capture_output=True, text=True, env=env)

        assert r.returncode == 0, r.stderr
        assert "REAL_CLAUDE_RAN --model x" in r.stdout  # real binary ran, got args
        assert "REAL_CLAUDE_RAN" not in r.stderr  # banner is on stderr, binary on stdout
        assert "url4 ensemble gateway" in r.stderr
        # the hostile expression printed literally ($prompt NOT expanded):
        assert "$prompt" in r.stderr
        assert "$(y)" in r.stderr

    @pytest.mark.usefixtures("_patch_profile")
    def test_add_exports_with_extra_lines_in_block(self, profile_file) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import (
            MARKER_BEGIN,
            MARKER_END,
            add_exports,
        )

        add_exports({"ANTHROPIC_BASE_URL": "http://127.0.0.1:9101"}, extra_lines=["claude() { :; }"])
        content = profile_file.read_text()
        assert 'export ANTHROPIC_BASE_URL="http://127.0.0.1:9101"' in content
        assert "claude() { :; }" in content
        assert content.index(MARKER_BEGIN) < content.index("claude() {") < content.index(MARKER_END)

    @pytest.mark.usefixtures("_patch_profile")
    def test_remove_exports_removes_extra_lines(self, profile_file) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import (
            MARKER_BEGIN,
            add_exports,
            remove_exports,
        )

        add_exports({"A": "1"}, extra_lines=["claude() { :; }"])
        remove_exports()
        content = profile_file.read_text()
        assert MARKER_BEGIN not in content
        assert "claude() {" not in content
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `uv run pytest -q src/screamingface/plugins/claude_env_intercept/tests/test_claude_env.py -k "banner or extra_lines"`
Expected: FAIL — `render_gateway_banner`/`build_claude_banner_function` don't exist; `add_exports` has no `extra_lines` kwarg.

- [ ] **Step 3: Implement in `shellenv.py`**

(a) Add `import shlex` near the top (after `from pathlib import Path`).

(b) Replace `add_exports` (current lines 37-57) — add the `extra_lines` param:

```python
def add_exports(env_vars: dict[str, str], extra_lines: list[str] | None = None) -> None:
    """Add a marker block of exports (and optional raw shell lines) to all shell profiles.

    Replaces any existing block to keep values current. ``extra_lines`` are written
    verbatim after the exports, inside the same marker block, so they are removed
    together with the exports on teardown.
    """
    lines = [MARKER_BEGIN]
    for key, value in env_vars.items():
        lines.append(f'export {key}="{value}"')
    if extra_lines:
        lines.extend(extra_lines)
    lines.append(MARKER_END)
    block = "\n".join(lines) + "\n"

    for profile in shell_profiles():
        content = profile.read_text() if profile.exists() else ""
        content = _strip_marker_block(content)

        if not content.endswith("\n") and content:
            content += "\n"

        profile.write_text(content + block)
        logger.info("Added exports to %s: %s", profile, list(env_vars.keys()))
```

(c) Add the renderer + builder at the end of the module (before `_strip_marker_block` is fine; anywhere at module scope):

```python
def render_gateway_banner(spec_name: str | None, expression: str | None) -> str:
    """Render the plain-text launch banner shown when the user starts ``claude``.

    Shows the active url4 spec + raw expression, or a warning when none is set.
    Plain ASCII (no ANSI) so it bakes cleanly into a shell rc file.
    """
    lines = [
        "  == ScreamingFace url4 ensemble gateway ==",
        "  Your claude queries are answered by this gateway, not api.anthropic.com.",
    ]
    if spec_name and expression:
        lines.append(f"  Active url4 spec: {spec_name}")
        lines.append(f"    {expression}")
    else:
        lines.append("  WARNING: no active url4 spec set — responses will be empty.")
        lines.append("    Set claude-frontend.active_spec in ScreamingFace settings.")
    return "\n".join(lines)


def build_claude_banner_function(banner_text: str) -> str:
    """Build a POSIX-sh ``claude()`` wrapper that prints ``banner_text`` to stderr
    then execs the real binary.

    One ``printf '%s\\n' '<quoted>' >&2`` per banner line, each quoted via
    ``shlex.quote`` so arbitrary url4 expressions cannot break out of the rc or be
    re-evaluated by the shell. ``command claude`` bypasses this function (no
    recursion); the banner never touches claude's stdout.
    """
    body = "\n".join(
        f"  printf '%s\\n' {shlex.quote(line)} >&2" for line in banner_text.split("\n")
    )
    return 'claude() {\n' + body + '\n  command claude "$@"\n}'
```

- [ ] **Step 4: Run, confirm PASS**

Run: `uv run pytest -q src/screamingface/plugins/claude_env_intercept/tests/test_claude_env.py`
Expected: PASS (incl. the sh/bash/zsh execution test — bash/zsh skip if not installed).

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/screamingface/plugins/claude_env_intercept/shellenv.py apps/server/src/screamingface/plugins/claude_env_intercept/tests/test_claude_env.py
git commit -m "feat(claude-env-intercept): render gateway banner + bake claude() wrapper into the shell block (SF-243)"
```

---

## Task 2: plugin setup() — inject the banner function

**Files:** `plugin.py`, `tests/test_claude_env.py`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_claude_env.py` (a new `class TestSetupBanner:` or inside the file; uses `_patch_profile`, mocks the app + cf plugin, and neutralizes launchctl):

```python
class TestSetupBanner:
    @pytest.mark.usefixtures("_patch_profile")
    def test_setup_writes_claude_banner_function(self, profile_file, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import screamingface.plugins.claude_env_intercept.plugin as plg

        # Neutralize launchctl side effects.
        monkeypatch.setattr(plg.subprocess, "run", lambda *a, **k: None)

        cf = MagicMock()
        cf.settings.active_spec = "cookbook"
        cf.settings.listen_host = "127.0.0.1"
        cf.settings.listen_port = 9101
        cf.get_active_expression.return_value = "(https://x/r.txt)!$prompt"

        app = MagicMock()
        app.state.plugins.active_plugins.get.return_value = cf

        plugin = plg.ClaudeEnvInterceptPlugin()
        plugin.setup(app, MagicMock(), MagicMock(), MagicMock())

        content = profile_file.read_text()
        assert 'export ANTHROPIC_BASE_URL="http://127.0.0.1:9101"' in content
        assert "claude() {" in content
        assert "cookbook" in content
        assert "$prompt" in content  # expression baked literally

    @pytest.mark.usefixtures("_patch_profile")
    def test_setup_no_active_spec_warns(self, profile_file, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import screamingface.plugins.claude_env_intercept.plugin as plg

        monkeypatch.setattr(plg.subprocess, "run", lambda *a, **k: None)
        cf = MagicMock()
        cf.settings.active_spec = None
        cf.settings.listen_host = "127.0.0.1"
        cf.settings.listen_port = 9101
        cf.get_active_expression.return_value = None
        app = MagicMock()
        app.state.plugins.active_plugins.get.return_value = cf

        plg.ClaudeEnvInterceptPlugin().setup(app, MagicMock(), MagicMock(), MagicMock())
        content = profile_file.read_text()
        assert "claude() {" in content
        assert "WARNING" in content
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `uv run pytest -q src/screamingface/plugins/claude_env_intercept/tests/test_claude_env.py::TestSetupBanner`
Expected: FAIL — `setup()` writes only the export, no `claude() {` function.

- [ ] **Step 3: Implement in `plugin.py`**

(a) Update the import (current lines 16):

```python
from screamingface.plugins.claude_env_intercept.shellenv import (
    add_exports,
    build_claude_banner_function,
    remove_exports,
    render_gateway_banner,
)
```

(b) In `setup()`, replace the `add_exports(env_vars)` call (current line 76) with banner injection (place after `env_vars` is built, line 73, and after `cf_settings` is in scope, line 69):

```python
        # Build the `claude` launcher banner from the active spec, baked into the
        # managed block so it shows at every `claude` launch (stderr only). Rendered
        # now (not at launch) — see plan: dynamic config lookup is unreliable from an
        # arbitrary shell cwd.
        banner = render_gateway_banner(
            cf_settings.active_spec,
            cf_plugin.get_active_expression(),
        )
        banner_fn = build_claude_banner_function(banner)

        # Write to shell profile: exports + the `claude` wrapper function.
        add_exports(env_vars, extra_lines=[banner_fn])
        logger.info("Claude Code env configured: ANTHROPIC_BASE_URL=%s", base_url)
```

(Remove the old `add_exports(env_vars)` + its existing log line so they aren't duplicated.)

- [ ] **Step 4: Run, confirm PASS**

Run: `uv run pytest -q src/screamingface/plugins/claude_env_intercept/tests/`
Expected: PASS (both `TestSetupBanner` tests + all existing tests, since `add_exports`'s new param is optional and back-compatible).

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/screamingface/plugins/claude_env_intercept/plugin.py apps/server/src/screamingface/plugins/claude_env_intercept/tests/test_claude_env.py
git commit -m "feat(claude-env-intercept): inject the url4 gateway banner into the claude launcher (SF-243)"
```

---

## Task 3: Full gate + PR

**Files:** none (verification).

- [ ] **Step 1: Types** — `cd apps/server && uv run pyright` → 0 errors.
- [ ] **Step 2: Full non-live suite (mirror CI)** — `cd apps/server && uv run pytest -q -m "not live" tests/ src/screamingface/plugins/` → PASS.
- [ ] **Step 3: Pre-commit** — `cd apps/server && pre-commit run --files src/screamingface/plugins/claude_env_intercept/shellenv.py src/screamingface/plugins/claude_env_intercept/plugin.py src/screamingface/plugins/claude_env_intercept/tests/test_claude_env.py`. If ruff-format reformats, re-stage + amend.
- [ ] **Step 4: Open PR** via superpowers:finishing-a-development-branch. Body references SF-243: the launcher banner, the bake-at-setup design + why dynamic was rejected, stderr-only safety. **Do NOT merge.**

---

## Residual risk / follow-ups (not blocking)
- **Static banner:** reflects `active_spec` at intercept activation; switching specs needs re-activation to refresh (same lifecycle as the `ANTHROPIC_BASE_URL` export). A truly-live banner would need a reliable cwd-independent config locator — a follow-up.
- **claude_intercept (DNS/SSL variant)** doesn't edit the shell profile, so it gets no banner; out of scope (claude-only, env-intercept path).
- **Non-login shells** that don't source these rc files won't define the function (same constraint as the existing `ANTHROPIC_BASE_URL` export).

---

## Self-Review
**Spec coverage:** banner at launch → `claude()` function in the managed block (Task 1/2); shows active spec + expression or warning → `render_gateway_banner` (Task 1, tested both ways); stderr-only + no stdout pollution + no recursion → `build_claude_banner_function` (Task 1, executed in sh/bash/zsh); teardown → automatic via `remove_exports` (Task 1 test). ✓
**Placeholder scan:** full code + concrete tests incl. a real-shell execution test with a hostile expression; no TODOs. ✓
**Type/name consistency:** `render_gateway_banner(spec_name: str|None, expression: str|None) -> str` and `build_claude_banner_function(banner_text: str) -> str` defined in `shellenv.py`, imported identically in `plugin.py`; `add_exports(env_vars, extra_lines=None)` signature matches all call sites (old positional call still valid). ✓
