# SF-199: E2E test — claude-frontend OAuth-access-token passthrough to real Anthropic

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an end-to-end test that exercises the configuration `Claude Code client (Authorization: Bearer <oauth-access-token>) → claude-frontend (transparent passthrough) → https://api.anthropic.com`. After SF-198 this path is covered only by unit tests with a mocked `httpx.AsyncClient`; the lone live test (`test_aigw_claude_e2e.py`) routes through aigateway, so claude-frontend's direct OAuth passthrough has never been exercised against real Anthropic.

**Architecture:** Add (1) a test-infrastructure helper that reads the OAuth access token from the macOS keychain (`Claude Code-credentials` → `claudeAiOauth.accessToken`); (2) an auth-mode switch on `ClaudeCodeClient` so test code can choose between `api_token` (`x-api-key`) and `oauth_access_token` (`Authorization: Bearer`); (3) a new e2e test file that boots SF with only the `claude-frontend` plugin (no aigateway), points it at real Anthropic, and asserts a 200.

**Tech Stack:** Python 3.13, pytest, FastAPI, macOS `security` CLI (`find-generic-password -w`), httpx.

**Asana ticket:** [SF-199](https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214853518025299)

**Depends on:** SF-198 / PR #173 must be merged before this branch is rebased onto `main` — this plan reuses `tests/e2e/infrastructure/claude_oauth.has_claude_code_oauth()` introduced in SF-198. Until then, the SF-199 branch carries an empty merge gap.

---

## Terminology

| Term | Header | Source |
|---|---|---|
| **API token** | `x-api-key: sk-ant-...` | console.anthropic.com → env (`ANTHROPIC_API_KEY`) |
| **OAuth access token** | `Authorization: Bearer ...` | macOS keychain `Claude Code-credentials`, field `claudeAiOauth.accessToken` |
| **OAuth refresh token** | (not on chat API) | Same keychain entry, field `claudeAiOauth.refreshToken` |

Throughout this plan, "OAuth" means the **OAuth access token** unless explicitly noted.

---

## File Structure

- **Create:** `apps/server/tests/e2e/infrastructure/claude_oauth_token.py` — reads the OAuth access token from the keychain. Test-infrastructure only; production proxy must not consume this.
- **Create:** `apps/server/tests/e2e/infrastructure/test_claude_oauth_token.py` — unit tests with mocked `subprocess.run`.
- **Modify:** `apps/server/tests/e2e/infrastructure/claude_code_client.py` — add `auth_mode` + `oauth_access_token` fields; switch header builder.
- **Create:** `apps/server/tests/e2e/test_claude_frontend_oauth_passthrough.py` — the new e2e test.

Out of scope:
- Production claude-frontend OAuth injection (PR #173 deliberately keeps the proxy transparent — Claude Code carries its own auth).
- Token refresh on expired tokens (test surfaces a clear error; user re-runs `claude /login`).
- YAML spec schema changes (deferred to a separate ticket if specs ever need auth-mode declarations).

---

### Task 1: OAuth-access-token reader helper

**Files:**
- Create: `apps/server/tests/e2e/infrastructure/claude_oauth_token.py`
- Test: `apps/server/tests/e2e/infrastructure/test_claude_oauth_token.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/server/tests/e2e/infrastructure/test_claude_oauth_token.py
"""Unit tests for read_claude_code_oauth_access_token."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from tests.e2e.infrastructure.claude_oauth_token import (
    OAuthExpiredError,
    OAuthMissingError,
    OAuthMalformedError,
    read_claude_code_oauth_access_token,
)

_FAR_FUTURE_MS = 9_999_999_999_999  # year 2286 — never expires within test runtime


def _completed(stdout: bytes, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


def _keychain_blob(*, access: str = "oauth-access-abc", expires_at_ms: int = _FAR_FUTURE_MS) -> bytes:
    return json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": access,
                "refreshToken": "ref-xyz",
                "expiresAt": expires_at_ms,
                "scopes": ["user:inference"],
            }
        }
    ).encode() + b"\n"


def test_returns_access_token_on_happy_path(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run", return_value=_completed(_keychain_blob(access="tkn-1"))
    ):
        assert read_claude_code_oauth_access_token() == "tkn-1"


def test_raises_missing_when_security_missing(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value=None):
        with pytest.raises(OAuthMissingError):
            read_claude_code_oauth_access_token()


def test_raises_missing_when_user_unset(monkeypatch) -> None:
    monkeypatch.delenv("USER", raising=False)
    with patch("shutil.which", return_value="/usr/bin/security"):
        with pytest.raises(OAuthMissingError):
            read_claude_code_oauth_access_token()


def test_raises_missing_when_returncode_nonzero(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run", return_value=_completed(b"", returncode=44)
    ):
        with pytest.raises(OAuthMissingError):
            read_claude_code_oauth_access_token()


def test_raises_expired_when_token_past_expiry(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run", return_value=_completed(_keychain_blob(expires_at_ms=1))
    ):
        with pytest.raises(OAuthExpiredError):
            read_claude_code_oauth_access_token()


def test_raises_malformed_when_json_broken(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run", return_value=_completed(b"{not-json")
    ):
        with pytest.raises(OAuthMalformedError):
            read_claude_code_oauth_access_token()


def test_raises_malformed_when_field_missing(monkeypatch) -> None:
    monkeypatch.setenv("USER", "alice")
    bad = json.dumps({"claudeAiOauth": {"refreshToken": "r", "expiresAt": _FAR_FUTURE_MS}}).encode()
    with patch("shutil.which", return_value="/usr/bin/security"), patch(
        "subprocess.run", return_value=_completed(bad)
    ):
        with pytest.raises(OAuthMalformedError):
            read_claude_code_oauth_access_token()
```

- [ ] **Step 2: Run tests, confirm they fail with ModuleNotFoundError**

```bash
cd apps/server
uv run pytest tests/e2e/infrastructure/test_claude_oauth_token.py -v
```

- [ ] **Step 3: Implement the helper**

```python
# apps/server/tests/e2e/infrastructure/claude_oauth_token.py
"""Read the Claude Code OAuth access token from the macOS keychain.

Test-infrastructure ONLY. Production code (the claude-frontend proxy) is
deliberately a transparent auth pass-through and must not consume this
helper — clients (Claude Code) attach their own auth. This helper exists
solely so e2e tests can emulate a Claude Code client that sends a real
Authorization: Bearer header to the proxy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

_KEYCHAIN_SERVICE = "Claude Code-credentials"
_TIMEOUT_SECONDS = 3


class OAuthMissingError(RuntimeError):
    """Keychain entry not present, or the security CLI is unavailable."""


class OAuthExpiredError(RuntimeError):
    """Keychain entry is present but the access token's expiresAt has passed."""


class OAuthMalformedError(RuntimeError):
    """Keychain blob isn't the expected Claude Code shape."""


def read_claude_code_oauth_access_token() -> str:
    """Return the current OAuth access token from the macOS keychain.

    Raises:
        OAuthMissingError: keychain entry absent, security CLI missing,
            or $USER not set.
        OAuthExpiredError: blob present but expiresAt is in the past.
        OAuthMalformedError: blob is not valid JSON or missing required
            fields.
    """
    if not shutil.which("security"):
        raise OAuthMissingError("macOS `security` CLI not on PATH")
    user = os.environ.get("USER", "")
    if not user:
        raise OAuthMissingError("$USER not set; cannot read keychain")
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
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise OAuthMissingError(f"keychain probe failed: {exc}") from exc
    if result.returncode != 0:
        raise OAuthMissingError(
            f"No keychain entry for {_KEYCHAIN_SERVICE!r}; run `claude /login`"
        )

    try:
        outer = json.loads(result.stdout)
        creds = outer["claudeAiOauth"]
        access_token = creds["accessToken"]
        expires_at_ms = int(creds["expiresAt"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise OAuthMalformedError(
            f"Claude Code keychain blob has unexpected shape: {exc}"
        ) from exc

    if time.time() * 1000 >= expires_at_ms:
        raise OAuthExpiredError(
            "OAuth access token has expired; run `claude /login` to refresh"
        )
    return access_token
```

- [ ] **Step 4: Run tests — all 7 must pass**

```bash
cd apps/server
uv run pytest tests/e2e/infrastructure/test_claude_oauth_token.py -v
```

- [ ] **Step 5: Ruff gates**

```bash
cd apps/server
uv run ruff check tests/e2e/infrastructure/claude_oauth_token.py tests/e2e/infrastructure/test_claude_oauth_token.py
uv run ruff format --check tests/e2e/infrastructure/claude_oauth_token.py tests/e2e/infrastructure/test_claude_oauth_token.py
```

- [ ] **Step 6: Commit**

```bash
git add apps/server/tests/e2e/infrastructure/claude_oauth_token.py \
        apps/server/tests/e2e/infrastructure/test_claude_oauth_token.py
git commit -m "test(e2e): add OAuth access-token reader for test client (SF-199)"
```

---

### Task 2: `ClaudeCodeClient` auth-mode switch

**Files:**
- Modify: `apps/server/tests/e2e/infrastructure/claude_code_client.py`
- Modify (append tests): `apps/server/tests/e2e/infrastructure/test_claude_oauth_token.py` (or new file — see step 1)

- [ ] **Step 1: Write the failing tests**

Add a new file `apps/server/tests/e2e/infrastructure/test_claude_code_client_auth.py`:

```python
# apps/server/tests/e2e/infrastructure/test_claude_code_client_auth.py
"""Unit tests for the ClaudeCodeClient auth-mode header builder."""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient


def _headers_for(client: ClaudeCodeClient) -> dict[str, str]:
    """Use the same private builder the client uses for real requests."""
    return client._auth_headers()  # noqa: SLF001 — exercising the boundary


def test_api_token_mode_emits_x_api_key() -> None:
    client = ClaudeCodeClient(proxy_url="http://x", api_key="sk-abc")
    headers = _headers_for(client)
    assert headers == {"x-api-key": "sk-abc"}


def test_oauth_access_token_mode_emits_bearer_and_oauth_betas() -> None:
    client = ClaudeCodeClient(
        proxy_url="http://x",
        auth_mode="oauth_access_token",
        oauth_access_token="tkn-1",
    )
    headers = _headers_for(client)
    assert headers["Authorization"] == "Bearer tkn-1"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["anthropic-beta"] == "oauth-2025-04-20"
    assert "x-api-key" not in headers


def test_oauth_mode_requires_token() -> None:
    client = ClaudeCodeClient(proxy_url="http://x", auth_mode="oauth_access_token")
    with pytest.raises(ValueError, match="oauth_access_token"):
        _headers_for(client)


def test_default_is_api_token_backward_compat() -> None:
    client = ClaudeCodeClient(proxy_url="http://x")
    assert client.auth_mode == "api_token"
    assert _headers_for(client) == {"x-api-key": "test-key"}
```

- [ ] **Step 2: Run and confirm failures**

```bash
cd apps/server
uv run pytest tests/e2e/infrastructure/test_claude_code_client_auth.py -v
```

Expected: AttributeError or TypeError — `auth_mode` and `_auth_headers` don't exist yet.

- [ ] **Step 3: Modify `claude_code_client.py`**

Read the current file first to confirm the dataclass shape (line ~68). Edit:

```python
# apps/server/tests/e2e/infrastructure/claude_code_client.py
# top of file: add imports
from typing import Literal

AuthMode = Literal["api_token", "oauth_access_token"]

# anthropic-beta needed for OAuth-token requests
_ANTHROPIC_VERSION = "2023-06-01"
_ANTHROPIC_OAUTH_BETA = "oauth-2025-04-20"
```

Inside the `@dataclass class ClaudeCodeClient:` block, change the existing fields:

```python
    proxy_url: str
    api_key: str = "test-key"            # used only when auth_mode == "api_token"
    auth_mode: AuthMode = "api_token"
    oauth_access_token: str | None = None  # required when auth_mode == "oauth_access_token"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
```

Add a new private method:

```python
    def _auth_headers(self) -> dict[str, str]:
        """Return the auth headers for the configured auth_mode."""
        if self.auth_mode == "api_token":
            return {"x-api-key": self.api_key}
        if self.auth_mode == "oauth_access_token":
            if not self.oauth_access_token:
                raise ValueError(
                    "auth_mode='oauth_access_token' requires oauth_access_token to be set"
                )
            return {
                "Authorization": f"Bearer {self.oauth_access_token}",
                "anthropic-version": _ANTHROPIC_VERSION,
                "anthropic-beta": _ANTHROPIC_OAUTH_BETA,
            }
        raise ValueError(f"unknown auth_mode: {self.auth_mode}")
```

Replace the line `headers = {"x-api-key": self.api_key}` (current line 130) with:

```python
        headers = self._auth_headers()
```

- [ ] **Step 4: Run all client tests — they must pass**

```bash
cd apps/server
uv run pytest tests/e2e/infrastructure/test_claude_code_client_auth.py -v
# Sanity: also run existing e2e tests that use the default mode — should not regress
uv run pytest tests/e2e/test_proxy_context_injection.py tests/e2e/test_proxy_multi_turn.py -v --no-header 2>&1 | tail -20
```

The proxy/multi-turn tests should still pass — they rely on the default `auth_mode="api_token"` and the unchanged default `api_key="test-key"`.

- [ ] **Step 5: Ruff gates**

```bash
cd apps/server
uv run ruff check tests/e2e/infrastructure/
uv run ruff format --check tests/e2e/infrastructure/
```

- [ ] **Step 6: Commit**

```bash
git add apps/server/tests/e2e/infrastructure/claude_code_client.py \
        apps/server/tests/e2e/infrastructure/test_claude_code_client_auth.py
git commit -m "test(e2e): add auth_mode switch to ClaudeCodeClient (SF-199)"
```

---

### Task 3: New e2e test — claude-frontend OAuth passthrough to real Anthropic

**Files:**
- Create: `apps/server/tests/e2e/test_claude_frontend_oauth_passthrough.py`

- [ ] **Step 1: Map the fixture layout**

Read `apps/server/tests/e2e/conftest.py` and `apps/server/tests/e2e/test_aigw_claude_e2e.py` to understand how SF-server fixtures are constructed. We need a fixture that boots SF with:
- `claude-frontend` plugin
- `tracing` plugin (optional, for span assertions)
- NO `aigateway`, NO `aigw-claude-backend`, NO `url4-executor`/`url4-specs`

The simplest path is to use `ServerManager` from `tests/e2e/infrastructure/server_manager.py` directly — same pattern as `test_aigw_claude_e2e.py`, but with a smaller plugin list and `upstream_url=https://api.anthropic.com`.

- [ ] **Step 2: Write the test**

```python
# apps/server/tests/e2e/test_claude_frontend_oauth_passthrough.py
"""E2E: claude-frontend transparent OAuth-access-token passthrough to real Anthropic.

This test pins the configuration SF-198 set up:

    Claude Code-style client (Authorization: Bearer <oauth-access-token>)
        --> claude-frontend (transparent passthrough, no env-var injection)
        --> https://api.anthropic.com (real)

The proxy MUST forward the Bearer header unchanged; it MUST NOT substitute
an API token or inject an env-var fallback. SF-198 removed the env-var
fallback; this test guarantees that the OAuth path still reaches Anthropic
and returns a 200.

Skipped on machines without a Claude Code keychain entry (re-using the
gating helper from tests/e2e/infrastructure/claude_oauth.py).
"""

from __future__ import annotations

import pytest

from tests.e2e.infrastructure.claude_code_client import ClaudeCodeClient
from tests.e2e.infrastructure.claude_oauth import has_claude_code_oauth
from tests.e2e.infrastructure.claude_oauth_token import (
    OAuthExpiredError,
    OAuthMalformedError,
    OAuthMissingError,
    read_claude_code_oauth_access_token,
)
from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = pytest.mark.e2e_live


def _config(proxy_port: int) -> dict:
    return {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": proxy_port, "reload": False, "ssl": False},
        "plugins": ["claude-frontend"],
        "plugin_config": {
            "claude-frontend": {
                "upstream_url": "https://api.anthropic.com",
            }
        },
    }


@pytest.fixture(scope="module")
def proxy_server():
    if not has_claude_code_oauth():
        pytest.skip("Claude Code OAuth credential not found in macOS keychain")

    proxy_port = ServerManager.pick_free_port()
    mgr = ServerManager(config=_config(proxy_port))
    mgr.start()
    try:
        yield mgr, proxy_port
    finally:
        mgr.stop()


@pytest.mark.timeout(60)
def test_oauth_access_token_passthrough_round_trip(
    proxy_server: tuple[ServerManager, int],
) -> None:
    """End-to-end 200 from real Anthropic via the proxy's OAuth passthrough."""
    _, proxy_port = proxy_server
    try:
        access_token = read_claude_code_oauth_access_token()
    except (OAuthMissingError, OAuthExpiredError, OAuthMalformedError) as exc:
        pytest.skip(f"Cannot read OAuth access token: {exc}")

    client = ClaudeCodeClient(
        proxy_url=f"http://127.0.0.1:{proxy_port}",
        auth_mode="oauth_access_token",
        oauth_access_token=access_token,
    )
    resp = client.send_message("Reply with exactly the word OK.", timeout=45)

    assert resp.status_code == 200, f"proxy responded {resp.status_code}: {resp.body}"
    # Anthropic's non-streaming response has a "content" list with at least
    # one text block. We don't pin the exact wording because the model may
    # politely paraphrase, but we DO require structured success.
    content = resp.body.get("content")
    assert isinstance(content, list) and content, f"unexpected body shape: {resp.body}"
    first = content[0]
    assert first.get("type") == "text"
    assert isinstance(first.get("text"), str) and first["text"].strip()
```

- [ ] **Step 3: Verify ServerManager's interface**

Read `apps/server/tests/e2e/infrastructure/server_manager.py` to confirm `pick_free_port`, the `config=` ctor kwarg, and `start()`/`stop()`. If the actual interface differs (e.g. it takes a YAML path or a different kwarg shape), adjust the fixture to match. **Do not invent ServerManager methods that don't exist** — read the file first.

If `ServerManager` has no `pick_free_port`, use `socket.socket()` + `bind((127.0.0.1, 0))` + `getsockname()[1]` inline.

If `ServerManager` only accepts a config-file path, write the config dict to a temp file via `tmp_path_factory` (request the fixture).

- [ ] **Step 4: Collection check**

```bash
cd apps/server
uv run pytest tests/e2e/test_claude_frontend_oauth_passthrough.py --collect-only -q
```

Expected: 1 test collected, no import errors.

- [ ] **Step 5: Run on a signed-in machine**

```bash
cd apps/server
uv run pytest tests/e2e/test_claude_frontend_oauth_passthrough.py -v -rs
```

Expected: 1 passed when the keychain is populated; 1 skipped otherwise (with the OAuth-not-found reason from `has_claude_code_oauth()`).

- [ ] **Step 6: Ruff gates**

```bash
cd apps/server
uv run ruff check tests/e2e/test_claude_frontend_oauth_passthrough.py
uv run ruff format --check tests/e2e/test_claude_frontend_oauth_passthrough.py
```

- [ ] **Step 7: Commit**

```bash
git add apps/server/tests/e2e/test_claude_frontend_oauth_passthrough.py
git commit -m "test(e2e): claude-frontend OAuth passthrough to real Anthropic (SF-199)"
```

---

### Task 4: Repo-wide gates, push, open PR

- [ ] **Step 1: Full local gates**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run ruff check .
uv run ruff format --check .
uv run pytest --ignore=tests/e2e -q          # unit tests must not regress
uv run pytest tests/e2e/infrastructure/test_claude_oauth_token.py \
              tests/e2e/infrastructure/test_claude_code_client_auth.py -v
```

Expected: all clean.

- [ ] **Step 2: Push branch**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin SF-199-e2e-oauth-passthrough
```

- [ ] **Step 3: Open PR (do NOT auto-merge)**

```bash
gh pr create --base main \
  --title "SF-199: E2E test for claude-frontend OAuth access-token passthrough" \
  --body "$(cat <<'EOF'
## Summary

Adds an end-to-end test that exercises the configuration `Claude Code (Authorization: Bearer <oauth-access-token>) → claude-frontend (transparent passthrough) → https://api.anthropic.com`. After SF-198 this path was covered only by unit tests with a mocked httpx; this PR fills the live-test gap.

Three pieces:
- New test-infrastructure helper `claude_oauth_token.py` that reads the OAuth access token from the macOS keychain (`Claude Code-credentials` → `claudeAiOauth.accessToken`). Test-only — production claude-frontend stays a transparent passthrough.
- `ClaudeCodeClient` gains an `auth_mode` switch (`"api_token"` vs `"oauth_access_token"`). Defaults to `"api_token"` for backward compatibility with existing e2e tests.
- New e2e test boots SF with only the `claude-frontend` plugin pointed at `https://api.anthropic.com`, sends a real Bearer-authed request, asserts a 200 with a well-formed Anthropic response.

Asana: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214853518025299

Depends on: SF-198 / #173.

## Test plan

- [ ] `uv run pytest tests/e2e/infrastructure/test_claude_oauth_token.py` — keychain reader unit tests pass (7 tests, all mocked).
- [ ] `uv run pytest tests/e2e/infrastructure/test_claude_code_client_auth.py` — auth-mode switch unit tests pass.
- [ ] `uv run pytest tests/e2e/test_claude_frontend_oauth_passthrough.py -v -rs` — on signed-in machine: 1 passed; on machine without keychain entry: 1 skipped with the SF-198 reason.
- [ ] `uv run pytest --ignore=tests/e2e` — no regressions to existing unit tests.
- [ ] `ruff check` and `ruff format --check` clean.
EOF
)"
```

- [ ] **Step 4: Comment PR URL on Asana**

```bash
curl -s -H "Authorization: Bearer $ASANA_PAT" -H "Content-Type: application/json" \
  -X POST "https://app.asana.com/api/1.0/tasks/1214853518025299/stories" \
  -d '{"data":{"text":"PR opened: <PR_URL_HERE>"}}'
```

---

## Self-Review

**Spec coverage:**
- Keychain reader (errors, expiry, malformed) → Task 1 ✓
- `ClaudeCodeClient` auth-mode switch → Task 2 ✓
- New live e2e test for OAuth passthrough → Task 3 ✓
- Gates + push + PR → Task 4 ✓

**Placeholders:** None. Every code block is concrete. Every command has an expected outcome.

**Type consistency:**
- `read_claude_code_oauth_access_token() -> str` defined in Task 1, called in Task 3.
- `AuthMode = Literal["api_token", "oauth_access_token"]` defined in Task 2, consumed in Task 3.
- Three error classes (`OAuthMissingError`, `OAuthExpiredError`, `OAuthMalformedError`) defined in Task 1, caught in Task 3.

**Risks / gotchas:**
- `ServerManager`'s exact ctor signature isn't known until Task 3 step 3 — the plan explicitly tells the implementer to read the file first rather than invent methods.
- The test calls real Anthropic and consumes a small amount of OAuth quota. Cost: trivial; latency: bounded by the 60-second test timeout.
- An expired OAuth token causes a skip, not a fail — this preserves CI cleanliness when developers haven't `/login`ed recently.
