"""Tests for the claude-backend plugin."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.claude_backend.models import ClaudeRunRequest
from screamingface.plugins.claude_backend.plugin import ClaudeBackendSettings
from screamingface.plugins.claude_backend.runner import build_args

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_app() -> FastAPI:
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        config = AppConfig(
            plugins=["url4-executor", "claude-backend"],
            plugin_config={"claude-backend": {}},
        )
        return create_app(config)


@pytest.fixture
def profile_app() -> FastAPI:
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        config = AppConfig(
            plugins=["url4-executor", "claude-backend"],
            plugin_config={
                "claude-backend": {
                    "profiles": {
                        "docs-review": {
                            "context": "(docs-a, docs-b)",
                            "system_prompt": "You review docs.",
                            "model": "claude-sonnet-4-20250514",
                            "effort": "high",
                        },
                        "quick": {
                            "system_prompt": "Be concise.",
                        },
                    },
                    "default_profile": "docs-review",
                },
            },
        )
        return create_app(config)


@pytest.fixture
def profile_client(profile_app: FastAPI) -> TestClient:
    return TestClient(profile_app)


@pytest.fixture
def cli_client(cli_app: FastAPI) -> TestClient:
    return TestClient(cli_app)


def _mock_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> AsyncMock:
    """Create a mock asyncio subprocess."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=stderr)
    proc.wait = AsyncMock()
    proc.kill = MagicMock()
    return proc


# ---------------------------------------------------------------------------
# Plugin discovery & settings
# ---------------------------------------------------------------------------


def test_plugin_discovered(cli_app: FastAPI) -> None:
    active = cli_app.state.plugins.active_plugins
    assert "claude-backend" in active


def test_settings_defaults() -> None:
    settings = ClaudeBackendSettings()
    assert settings.default_model is None
    assert settings.default_effort == "medium"
    assert settings.timeout_seconds == 300.0
    assert settings.max_budget_usd is None
    assert settings.permission_mode is None
    assert settings.dangerously_skip_permissions is False


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_CLAUDE_BACKEND__DEFAULT_MODEL", "claude-sonnet-4-20250514")
    settings = ClaudeBackendSettings()
    assert settings.default_model == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# build_args
# ---------------------------------------------------------------------------


def test_build_args_minimal() -> None:
    request = ClaudeRunRequest(prompt="hello")
    settings = ClaudeBackendSettings()
    args = build_args(request, settings)
    assert args[:2] == ["claude", "-p"]
    assert "--effort" in args
    idx = args.index("--effort")
    assert args[idx + 1] == "medium"
    assert "--no-session-persistence" in args


def test_build_args_full() -> None:
    request = ClaudeRunRequest(
        prompt="do stuff",
        model="claude-opus-4-20250514",
        system_prompt="be helpful",
        append_system_prompt="also be concise",
        output_format="json",
        json_schema={"type": "object"},
        max_budget_usd=5.0,
        effort="high",
        tools=["bash", "read"],
        allowed_tools=["write"],
        disallowed_tools=["delete"],
        mcp_config="/path/to/mcp.json",
        permission_mode="plan",
        add_dirs=["/tmp/work"],
        fallback_model="claude-sonnet-4-20250514",
        dangerously_skip_permissions=True,
        no_session_persistence=False,
    )
    settings = ClaudeBackendSettings()
    args = build_args(request, settings, temp_dir="/tmp/tempfiles")

    assert "--model" in args
    assert "claude-opus-4-20250514" in args
    assert "--system-prompt" in args
    assert "--append-system-prompt" in args
    assert "--output-format" in args
    assert "json" in args
    assert "--json-schema" in args
    assert "--max-budget-usd" in args
    assert "5.0" in args
    assert "--effort" in args
    assert "high" in args
    assert args.count("--tools") == 2
    assert "--allowed-tools" in args
    assert "--disallowed-tools" in args
    assert "--mcp-config" in args
    assert "--permission-mode" in args
    assert "plan" in args
    # add_dirs: explicit /tmp/work + temp_dir
    add_dir_indices = [i for i, a in enumerate(args) if a == "--add-dir"]
    add_dir_values = [args[i + 1] for i in add_dir_indices]
    assert "/tmp/work" in add_dir_values
    assert "/tmp/tempfiles" in add_dir_values
    assert "--fallback-model" in args
    assert "--dangerously-skip-permissions" in args
    assert "--no-session-persistence" not in args


# ---------------------------------------------------------------------------
# POST /claude/run — non-streaming
# ---------------------------------------------------------------------------


def test_run_success(cli_client: TestClient) -> None:
    proc = _mock_process(stdout=b"Hello from Claude!", stderr=b"")
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = cli_client.post("/claude/run", json={"prompt": "hello"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ec"] == 0
    assert data["so"] == "Hello from Claude!"
    assert data["se"] == ""
    assert data["ds"] >= 0


def test_run_cli_error(cli_client: TestClient) -> None:
    proc = _mock_process(stdout=b"", stderr=b"Error: something broke", returncode=1)
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = cli_client.post("/claude/run", json={"prompt": "hello"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ec"] == 1
    assert "something broke" in data["se"]


def test_run_timeout(cli_client: TestClient) -> None:
    proc = _mock_process()
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = cli_client.post(
            "/claude/run",
            json={"prompt": "hello", "timeout_seconds": 0.001},
        )

    assert resp.status_code == 504


def test_run_with_files(cli_client: TestClient) -> None:
    proc = _mock_process(stdout=b"processed")
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ) as mock_exec:
        resp = cli_client.post(
            "/claude/run",
            json={
                "prompt": "analyze this",
                "files": [
                    {"filename": "main.py", "content": "print('hi')"},
                    {"filename": "sub/helper.py", "content": "def f(): pass"},
                ],
            },
        )

    assert resp.status_code == 200
    # The args should include --add-dir pointing to a temp directory
    call_args = mock_exec.call_args[0]
    assert "--add-dir" in call_args


def test_path_traversal_rejected(cli_client: TestClient) -> None:
    resp = cli_client.post(
        "/claude/run",
        json={
            "prompt": "hack",
            "files": [{"filename": "../etc/passwd", "content": "evil"}],
        },
    )
    assert resp.status_code == 400
    assert "traversal" in resp.json()["detail"].lower()


def test_run_json_output(cli_client: TestClient) -> None:
    payload = {"answer": 42, "reasoning": "because"}
    proc = _mock_process(stdout=json.dumps(payload).encode())
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = cli_client.post(
            "/claude/run",
            json={"prompt": "answer", "output_format": "json"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["r"] == payload
    assert data["ec"] == 0


def test_run_streaming(cli_client: TestClient) -> None:
    async def fake_stdout_iter():
        for line in [b'{"type":"text","text":"hi"}\n', b'{"type":"text","text":"bye"}\n']:
            yield line

    proc = _mock_process()
    proc.stdout.__aiter__ = lambda self: fake_stdout_iter()
    proc.stderr.read = AsyncMock(return_value=b"")

    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = cli_client.post(
            "/claude/run",
            json={"prompt": "hello", "output_format": "stream-json"},
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "data:" in body


# ---------------------------------------------------------------------------
# Alias acceptance
# ---------------------------------------------------------------------------


def test_alias_acceptance(cli_client: TestClient) -> None:
    """POST with short aliases is accepted."""
    proc = _mock_process(stdout=b"ok", stderr=b"")
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = cli_client.post(
            "/claude/run",
            json={"p": "hello", "e": "high", "m": "claude-sonnet-4-20250514"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ec"] == 0
    assert data["so"] == "ok"


def test_long_name_acceptance(cli_client: TestClient) -> None:
    """POST with long field names is still accepted."""
    proc = _mock_process(stdout=b"ok", stderr=b"")
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = cli_client.post(
            "/claude/run",
            json={"prompt": "hello", "effort": "high", "model": "claude-sonnet-4-20250514"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ec"] == 0
    assert data["so"] == "ok"


# ---------------------------------------------------------------------------
# Profile settings
# ---------------------------------------------------------------------------


def test_profile_settings_defaults() -> None:
    settings = ClaudeBackendSettings()
    assert settings.profiles == {}
    assert settings.default_profile is None


def test_profile_invalid_name_rejected() -> None:
    with pytest.raises(Exception, match="Invalid profile name"):
        ClaudeBackendSettings(profiles={"INVALID NAME!": {}})


# ---------------------------------------------------------------------------
# Profile routes
# ---------------------------------------------------------------------------


def test_profile_get_resolves(profile_client: TestClient) -> None:
    proc = _mock_process(stdout=b"Claude says hi", stderr=b"")
    with (
        patch(
            "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc,
        ),
        patch(
            "screamingface.plugins.url4_executor.url4._fetch_url",
            new_callable=AsyncMock,
            return_value="fetched docs",
        ),
    ):
        resp = profile_client.get("/claude/docs-review?prompt=summarize")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ec"] == 0
    assert data["so"] == "Claude says hi"


def test_profile_no_context(profile_client: TestClient) -> None:
    """Profile without context field works (no url4 resolution needed)."""
    proc = _mock_process(stdout=b"concise reply", stderr=b"")
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = profile_client.get("/claude/quick?prompt=hello")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ec"] == 0
    assert data["so"] == "concise reply"


def test_profile_context_override(profile_client: TestClient) -> None:
    """Query param context overrides profile's default context."""
    proc = _mock_process(stdout=b"overridden", stderr=b"")
    with (
        patch(
            "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc,
        ),
        patch(
            "screamingface.plugins.url4_executor.url4._fetch_url",
            new_callable=AsyncMock,
            return_value="custom content",
        ),
    ):
        resp = profile_client.get(
            "/claude/docs-review?prompt=review&context=http://other.com"
        )

    assert resp.status_code == 200
    assert resp.json()["ec"] == 0


def test_profile_not_found(profile_client: TestClient) -> None:
    resp = profile_client.get("/claude/nonexistent?prompt=hello")
    assert resp.status_code == 404
    assert "nonexistent" in resp.json()["detail"]


def test_profile_prompt_required(profile_client: TestClient) -> None:
    resp = profile_client.get("/claude/docs-review")
    assert resp.status_code == 422


def test_profile_post(profile_client: TestClient) -> None:
    """POST to profile endpoint works for large prompts."""
    proc = _mock_process(stdout=b"posted", stderr=b"")
    with patch(
        "screamingface.plugins.claude_backend.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = profile_client.post("/claude/quick?prompt=hello")

    assert resp.status_code == 200
    assert resp.json()["so"] == "posted"
