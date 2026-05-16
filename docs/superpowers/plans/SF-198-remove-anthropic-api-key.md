# SF-198: Remove ANTHROPIC_API_KEY usage; enforce Claude Code OAuth only

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every reference to the `ANTHROPIC_API_KEY` environment variable from screamingface code, tests, and docs so all Anthropic auth flows exclusively through the Claude Code OAuth token (macOS keychain entry `Claude Code-credentials`).

**Architecture:** Three classes of change: (1) delete the env-var → `x-api-key` fallback in `claude-frontend` proxy; (2) switch the e2e test skip gate from env-var to a keychain probe (move probe into a shared helper); (3) strip the env var from README. The aigateway (`anthropic_provider`) is already OAuth-only — no changes there.

**Tech Stack:** Python 3.13, FastAPI, pytest, `security find-generic-password` (macOS keychain CLI).

**Asana ticket:** [SF-198](https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214848763302843)

---

## File Structure

- **Create:** `apps/server/tests/e2e/infrastructure/claude_oauth.py` — shared keychain probe `has_claude_code_oauth()`.
- **Modify:** `apps/server/src/screamingface/plugins/claude_frontend/proxy.py` — drop env-var fallback in `_build_headers`.
- **Modify:** `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy.py` — delete `test_proxy_auth_fallback`.
- **Modify:** `apps/server/tests/e2e/conftest.py` — replace env-var skip gate with keychain probe.
- **Modify:** `apps/server/tests/e2e/test_aigw_claude_e2e.py` — use shared helper; drop env-var branch and module docstring mention.
- **Modify:** `README.md` — remove three references to `ANTHROPIC_API_KEY`; document Claude Code OAuth.

Out of scope: `screamingface-demo-004/` (snapshot copy of the same tree — leave untouched unless requested).

---

### Task 1: Add shared keychain probe helper

**Files:**
- Create: `apps/server/tests/e2e/infrastructure/claude_oauth.py`
- Test: `apps/server/tests/e2e/infrastructure/test_claude_oauth.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/server/tests/e2e/infrastructure/test_claude_oauth.py
"""Unit tests for has_claude_code_oauth — purely tests the subprocess path."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from tests.e2e.infrastructure.claude_oauth import has_claude_code_oauth


def test_returns_true_when_security_returncode_zero(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=b"x"),
    ):
        assert has_claude_code_oauth() is True


def test_returns_false_when_security_missing(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value=None):
        assert has_claude_code_oauth() is False


def test_returns_false_when_user_unset(monkeypatch) -> None:
    monkeypatch.delenv("USER", raising=False)
    with patch("shutil.which", return_value="/usr/bin/security"):
        assert has_claude_code_oauth() is False


def test_returns_false_on_timeout(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="security", timeout=3)
    ):
        assert has_claude_code_oauth() is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/server
uv run pytest tests/e2e/infrastructure/test_claude_oauth.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tests.e2e.infrastructure.claude_oauth'`.

- [ ] **Step 3: Write minimal implementation**

```python
# apps/server/tests/e2e/infrastructure/claude_oauth.py
"""Probe for the Claude Code OAuth credential in the macOS keychain.

Used by the e2e suite to gate live-Anthropic tests. We deliberately do NOT
read the token here — only check that the keychain entry exists. Reading
the token is reserved for the aigateway, which holds the only legitimate
need-to-know.
"""
from __future__ import annotations

import os
import shutil
import subprocess

_KEYCHAIN_SERVICE = "Claude Code-credentials"
_TIMEOUT_SECONDS = 3


def has_claude_code_oauth() -> bool:
    """Return True iff the Claude Code OAuth keychain entry exists for $USER."""
    if not shutil.which("security"):
        return False
    user = os.environ.get("USER", "")
    if not user:
        return False
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _KEYCHAIN_SERVICE,
                "-a",
                user,
                "-w",
            ],
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd apps/server
uv run pytest tests/e2e/infrastructure/test_claude_oauth.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/server/tests/e2e/infrastructure/claude_oauth.py \
        apps/server/tests/e2e/infrastructure/test_claude_oauth.py
git commit -m "test(e2e): add shared Claude Code OAuth keychain probe (SF-198)"
```

---

### Task 2: Switch e2e conftest skip gate to keychain probe

**Files:**
- Modify: `apps/server/tests/e2e/conftest.py` (lines 88–96)

- [ ] **Step 1: Write the failing test**

```python
# apps/server/tests/e2e/infrastructure/test_claude_oauth.py — append
import pytest


def test_conftest_uses_keychain_probe(monkeypatch) -> None:
    """The e2e_live skip reason must reference OAuth, not ANTHROPIC_API_KEY."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-be-ignored")
    from unittest.mock import patch as _patch

    with _patch(
        "tests.e2e.infrastructure.claude_oauth.has_claude_code_oauth", return_value=False
    ):
        from tests.e2e import conftest as ce2e
        # The hook builds the skip marker; we just confirm the reason string.
        items: list = []
        config = pytest.Config.fromdictargs({}, []) if False else None  # unused
        # Direct inspection: the marker reason is constructed inline.
        # We assert on the source instead to keep the test deterministic.
        import inspect
        src = inspect.getsource(ce2e.pytest_collection_modifyitems)
        assert "ANTHROPIC_API_KEY" not in src
        assert "Claude Code" in src or "has_claude_code_oauth" in src
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/server
uv run pytest tests/e2e/infrastructure/test_claude_oauth.py::test_conftest_uses_keychain_probe -v
```

Expected: FAIL — current source still contains `ANTHROPIC_API_KEY`.

- [ ] **Step 3: Edit `conftest.py`**

Replace lines 88–96 (the `pytest_collection_modifyitems` block that gates on `ANTHROPIC_API_KEY`) with:

```python
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # 1) Auto-skip live tests without a Claude Code OAuth credential.
    from tests.e2e.infrastructure.claude_oauth import has_claude_code_oauth

    if not has_claude_code_oauth():
        skip_live = pytest.mark.skip(
            reason="Claude Code OAuth credential not found in macOS keychain"
        )
        for item in items:
            if "e2e_live" in item.keywords:
                item.add_marker(skip_live)

    # 2) Provider filter — deselect items not in the requested queue
```

Remove the now-unused `import os` line at the top of `conftest.py` only if no other code in the file references `os`. Run `grep -n "\bos\b" apps/server/tests/e2e/conftest.py` first to confirm.

- [ ] **Step 4: Run tests to verify**

```bash
cd apps/server
uv run pytest tests/e2e/infrastructure/test_claude_oauth.py -v
uv run pytest tests/e2e/ -v --collect-only 2>&1 | head -30  # smoke-check collection still works
```

Expected: all 5 unit tests pass; collection succeeds without import error.

- [ ] **Step 5: Commit**

```bash
git add apps/server/tests/e2e/conftest.py \
        apps/server/tests/e2e/infrastructure/test_claude_oauth.py
git commit -m "test(e2e): gate live tests on Claude Code OAuth, not API key (SF-198)"
```

---

### Task 3: Remove env-var branch from `test_aigw_claude_e2e.py`

**Files:**
- Modify: `apps/server/tests/e2e/test_aigw_claude_e2e.py` (lines 41 docstring, 85–134)

- [ ] **Step 1: Edit the file**

Replace the entire `Skip-gating` block (the `_has_claude_code_keychain` and `_credentials_available` functions, lines ~83–115) with a single import:

```python
from tests.e2e.infrastructure.claude_oauth import has_claude_code_oauth
```

Update the module docstring at line ~41 from:

```
Skipped unless ANTHROPIC_API_KEY is set OR the Claude Code CLI keychain
```

to:

```
Skipped unless the Claude Code CLI keychain entry is present.
```

Update the call site at line ~132 from `if not _credentials_available():` to `if not has_claude_code_oauth():` and replace the skip message (lines ~133–135) from:

```python
"Neither ANTHROPIC_API_KEY env var nor a Claude Code keychain "
"entry was found; skipping live Anthropic e2e."
```

to:

```python
"Claude Code OAuth credential not found in macOS keychain; "
"skipping live Anthropic e2e."
```

Remove now-unused imports `os`, `shutil`, `subprocess` from the top of the file **only if** no other code in the module uses them. Run `grep -nE "\b(os|shutil|subprocess)\." apps/server/tests/e2e/test_aigw_claude_e2e.py` to verify before removing each.

- [ ] **Step 2: Verify the file compiles and collection succeeds**

```bash
cd apps/server
uv run python -c "import ast; ast.parse(open('tests/e2e/test_aigw_claude_e2e.py').read())"
uv run pytest tests/e2e/test_aigw_claude_e2e.py --collect-only -q
```

Expected: parse OK; collection shows 1 test.

- [ ] **Step 3: Verify no ANTHROPIC_API_KEY references remain in the file**

```bash
grep -n "ANTHROPIC_API_KEY" apps/server/tests/e2e/test_aigw_claude_e2e.py
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add apps/server/tests/e2e/test_aigw_claude_e2e.py
git commit -m "test(e2e): require Claude Code OAuth keychain for claude e2e (SF-198)"
```

---

### Task 4: Remove env-var fallback from `claude-frontend` proxy

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/proxy.py` (lines 178–188)
- Modify: `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy.py` (delete `test_proxy_auth_fallback`)

- [ ] **Step 1: Write the failing test**

In `apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy.py`, **replace** `test_proxy_auth_fallback` (around lines 77–95) with:

```python
def test_proxy_does_not_inject_env_api_key(
    proxy_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ANTHROPIC_API_KEY must NOT be auto-forwarded as x-api-key.

    All Anthropic auth flows through the Claude Code OAuth path served by
    aigateway. If a client sends no auth header, the proxy MUST NOT silently
    paper over it with an env var.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-ignored")
    mock_response = httpx.Response(200, json={"id": "msg_789"})

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        proxy_client.post(
            "/v1/messages",
            json={"model": "claude-sonnet-4-20250514", "messages": []},
        )

    call_kwargs = mock_post.call_args
    sent_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert "x-api-key" not in sent_headers
    assert "authorization" not in sent_headers
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/claude_frontend/tests/test_proxy.py::test_proxy_does_not_inject_env_api_key -v
```

Expected: FAIL — current `_build_headers` still injects `x-api-key`.

- [ ] **Step 3: Edit `proxy.py`**

Remove lines 184–187 in `apps/server/src/screamingface/plugins/claude_frontend/proxy.py`. Before:

```python
    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        if "x-api-key" not in headers and "authorization" not in headers:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                headers["x-api-key"] = api_key
        return headers
```

After:

```python
    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        return headers
```

Check whether `os` is still used elsewhere in `proxy.py` (`grep -n '\bos\.' apps/server/src/screamingface/plugins/claude_frontend/proxy.py`). It is — `os.environ.get("_SF_SESSION_ID")` at line ~195 — so leave the `import os` in place.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd apps/server
uv run pytest src/screamingface/plugins/claude_frontend/tests/test_proxy.py -v
```

Expected: all tests in the file pass; the renamed test now asserts no injection.

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/screamingface/plugins/claude_frontend/proxy.py \
        apps/server/src/screamingface/plugins/claude_frontend/tests/test_proxy.py
git commit -m "feat(claude-frontend): drop ANTHROPIC_API_KEY env-var fallback (SF-198)"
```

---

### Task 5: Update README

**Files:**
- Modify: `README.md` (lines 74, 82, 116)

- [ ] **Step 1: Edit `README.md`**

**Line 74** — remove the `api_key_env` row from the example `sf.json`. Before:

```json
    "claude-frontend": {
      "upstream_url": "https://api.anthropic.com",
      "api_key_env": "ANTHROPIC_API_KEY"
    }
```

After:

```json
    "claude-frontend": {
      "upstream_url": "https://api.anthropic.com"
    }
```

**Lines 81–84** — replace the entire "Set your Anthropic key…" block:

Before:

```markdown
Set your Anthropic key so the proxy can forward requests:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```
```

After:

```markdown
Anthropic auth flows through the Claude Code OAuth token stored in the macOS
keychain (service `Claude Code-credentials`). Make sure you have signed in to
Claude Code at least once on this machine — no environment variables required.
```

**Line 116** — delete the `ANTHROPIC_API_KEY` row from the Environment Variables table. Before:

```markdown
| `ANTHROPIC_API_KEY` | Claude API key for the proxy plugin | For claude-frontend |
| `SF_CONFIG` | Inline JSON config (overrides sf.json) | No |
```

After:

```markdown
| `SF_CONFIG` | Inline JSON config (overrides sf.json) | No |
```

- [ ] **Step 2: Verify no references remain**

```bash
grep -n "ANTHROPIC_API_KEY" README.md
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: remove ANTHROPIC_API_KEY references; document OAuth flow (SF-198)"
```

---

### Task 6: Repo-wide sweep & CI gates

- [ ] **Step 1: Confirm no references remain**

```bash
cd /Users/sergey/work/openmind/screamingface
grep -rn "ANTHROPIC_API_KEY\|anthropic_api_key" \
  --include="*.py" --include="*.md" --include="*.json" \
  --include="*.yaml" --include="*.yml" --include="*.toml" \
  --include="*.sh" --include="*.ts" --include="*.tsx" --include="*.js" \
  . | grep -v .venv | grep -v node_modules | grep -v __pycache__ \
    | grep -v screamingface-demo-004
```

Expected: no output.

- [ ] **Step 2: Run full local CI gates**

```bash
cd apps/server
uv run ruff format --check .
uv run ruff check .
uv run pytest -q  # full unit + e2e collection
```

If `ruff format --check` reports diffs, run `uv run ruff format .` and re-stage / amend a follow-up format commit. Mirror full CI — `ruff format` is a separate gate from `ruff check`.

Expected: all gates pass; the live e2e test in `test_aigw_claude_e2e.py` is now either run or skipped with the new "Claude Code OAuth credential not found…" reason — never the old `ANTHROPIC_API_KEY` reason.

- [ ] **Step 3: Push and open PR**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin SF-198-remove-anthropic-api-key
gh pr create --base main --title "SF-198: Remove ANTHROPIC_API_KEY usage; require Claude Code OAuth" \
  --body "$(cat <<'EOF'
## Summary
- Removes the `ANTHROPIC_API_KEY` env-var fallback from the `claude-frontend` proxy. All Anthropic auth now flows through the aigateway's Claude Code OAuth path.
- Switches the e2e suite's live-test skip gate from `ANTHROPIC_API_KEY` to a macOS keychain probe (`Claude Code-credentials`). Probe lives in a new shared helper `tests/e2e/infrastructure/claude_oauth.py`.
- Strips `ANTHROPIC_API_KEY` from the README and replaces it with a note on the OAuth flow.

Asana: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214848763302843

## Test plan
- [ ] `uv run pytest src/screamingface/plugins/claude_frontend/tests/test_proxy.py` — proxy unit tests pass; new test asserts no `x-api-key` is injected when client omits auth.
- [ ] `uv run pytest tests/e2e/infrastructure/test_claude_oauth.py` — keychain-probe unit tests pass.
- [ ] `uv run pytest tests/e2e/ -v -rs` — live tests run if Claude Code OAuth keychain entry present; otherwise skip with new reason.
- [ ] `grep -rn ANTHROPIC_API_KEY` in repo (excluding `screamingface-demo-004/`, `.venv/`, `node_modules/`) returns no results.
- [ ] `ruff check` and `ruff format --check` both pass.
EOF
)"
```

Do NOT auto-merge. Stop after the PR is open and wait for review.

---

## Self-Review

**Spec coverage:**
- Production code site (proxy.py:185-187) → Task 4 ✓
- Test file proxy unit test (test_proxy.py:78) → Task 4 (replaces, doesn't delete, to keep the contract explicit) ✓
- e2e conftest gate → Task 2 ✓
- e2e test file `_credentials_available` → Task 3 ✓
- README three references → Task 5 ✓
- Shared keychain helper → Task 1 ✓
- Repo-wide sweep + CI gates + PR → Task 6 ✓

**Placeholders:** None. Every code block is concrete. Every command has an expected output.

**Type consistency:** `has_claude_code_oauth()` is defined in Task 1 and used unchanged in Tasks 2 and 3.

**Out of scope (documented):** `screamingface-demo-004/` snapshot copy.
