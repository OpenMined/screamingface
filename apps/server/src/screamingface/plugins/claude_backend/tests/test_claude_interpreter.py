"""Tests for the ClaudeInterpreter — url4 expressions through Claude CLI."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.claude_backend.interpreter import ClaudeInterpreter
from screamingface.plugins.claude_backend.plugin import ClaudeBackendSettings

_RUN_CLAUDE = "screamingface.plugins.claude_backend.interpreter.run_claude"
_FETCH_URL = "screamingface.plugins.url4_executor.url4._fetch_url"


# ---------------------------------------------------------------------------
# Unit tests — ClaudeInterpreter
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> ClaudeBackendSettings:
    return ClaudeBackendSettings()


def test_build_args_default(settings: ClaudeBackendSettings) -> None:
    interp = ClaudeInterpreter(settings=settings)
    args = interp._build_args()
    assert args[0] == "claude"
    assert "-p" in args
    assert "--system-prompt" in args
    assert settings.interpreter_system_prompt in args


def test_build_args_with_model() -> None:
    s = ClaudeBackendSettings(default_model="claude-haiku-4-5-20251001")
    interp = ClaudeInterpreter(settings=s)
    args = interp._build_args()
    assert "--model" in args
    assert "claude-haiku-4-5-20251001" in args


def test_build_args_no_settings() -> None:
    interp = ClaudeInterpreter()
    args = interp._build_args()
    assert args == ["claude", "-p"]


def test_process_combines_intent_and_sources(
    settings: ClaudeBackendSettings,
) -> None:
    interp = ClaudeInterpreter(settings=settings)

    async def _run():
        with patch(
            _RUN_CLAUDE,
            new_callable=AsyncMock,
            return_value=(0, "result", "", 1.0),
        ) as mock:
            result = await interp.process("source text", "question")
        return result, mock

    result, mock = asyncio.run(_run())
    assert result == "result"
    prompt = mock.call_args[0][1]
    assert "question" in prompt
    assert "source text" in prompt


def test_process_sources_only(settings: ClaudeBackendSettings) -> None:
    interp = ClaudeInterpreter(settings=settings)

    async def _run():
        with patch(
            _RUN_CLAUDE,
            new_callable=AsyncMock,
            return_value=(0, "out", "", 1.0),
        ) as mock:
            await interp.process("only sources", None)
        return mock

    mock = asyncio.run(_run())
    assert mock.call_args[0][1] == "only sources"


def test_process_intent_only(settings: ClaudeBackendSettings) -> None:
    interp = ClaudeInterpreter(settings=settings)

    async def _run():
        with patch(
            _RUN_CLAUDE,
            new_callable=AsyncMock,
            return_value=(0, "out", "", 1.0),
        ) as mock:
            await interp.process("", "just intent")
        return mock

    mock = asyncio.run(_run())
    assert mock.call_args[0][1] == "just intent"


def test_process_runs_in_temp_dir(settings: ClaudeBackendSettings) -> None:
    interp = ClaudeInterpreter(settings=settings)
    captured_cwd: list[str | None] = [None]

    async def capture_cwd(args, prompt, timeout, cwd=None):
        captured_cwd[0] = cwd
        return (0, "ok", "", 1.0)

    async def _run():
        with patch(_RUN_CLAUDE, side_effect=capture_cwd):
            await interp.process("src", "intent")

    asyncio.run(_run())
    assert captured_cwd[0] is not None
    assert not os.path.exists(captured_cwd[0])


def test_evaluate_text_intent(settings: ClaudeBackendSettings) -> None:
    interp = ClaudeInterpreter(settings=settings)

    async def _run():
        with patch(
            _RUN_CLAUDE,
            new_callable=AsyncMock,
            return_value=(0, "answer", "", 1.0),
        ):
            return await interp.evaluate("hello!summarize")

    assert asyncio.run(_run()) == "answer"


def test_evaluate_with_fetched_source(
    settings: ClaudeBackendSettings,
) -> None:
    interp = ClaudeInterpreter(settings=settings)

    async def _run():
        with (
            patch(_FETCH_URL, new_callable=AsyncMock, return_value="fetched"),
            patch(
                _RUN_CLAUDE,
                new_callable=AsyncMock,
                return_value=(0, "analysis", "", 1.0),
            ) as mock,
        ):
            result = await interp.evaluate("(http://example.com)!analyze this")
        return result, mock

    result, mock = asyncio.run(_run())
    assert result == "analysis"
    prompt = mock.call_args[0][1]
    assert "analyze this" in prompt
    assert "fetched" in prompt


# ---------------------------------------------------------------------------
# Integration — GET /claude?q= endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def claude_app() -> FastAPI:
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        config = AppConfig(
            plugins=["url4-executor", "data-store", "claude-backend"],
            plugin_config={"claude-backend": {}},
        )
        return create_app(config)


@pytest.fixture
def claude_client(claude_app: FastAPI) -> TestClient:
    return TestClient(claude_app)


def test_claude_url4_endpoint(claude_client: TestClient) -> None:
    with patch(
        _RUN_CLAUDE,
        new_callable=AsyncMock,
        return_value=(0, "cli output", "", 1.0),
    ):
        resp = claude_client.get("/claude", params={"q": "hello!summarize"})

    assert resp.status_code == 200
    assert "cli output" in resp.text


def test_claude_url4_missing_q(claude_client: TestClient) -> None:
    resp = claude_client.get("/claude")
    assert resp.status_code == 422


def test_claude_url4_error_502(claude_client: TestClient) -> None:
    with patch(
        _RUN_CLAUDE,
        new_callable=AsyncMock,
        side_effect=Exception("CLI crashed"),
    ):
        resp = claude_client.get("/claude", params={"q": "hello!test"})

    assert resp.status_code == 502
    assert "failed" in resp.json()["detail"].lower()
