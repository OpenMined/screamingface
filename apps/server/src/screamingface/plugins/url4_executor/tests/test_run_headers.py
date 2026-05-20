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

    app_with_executor.state.hooks.register(
        HOOK_RUN_STARTED, _spy(HOOK_RUN_STARTED), plugin_name="spy"
    )
    app_with_executor.state.hooks.register(
        HOOK_RUN_FINISHED, _spy(HOOK_RUN_FINISHED), plugin_name="spy"
    )
    app_with_executor.state.hooks.register(
        HOOK_RUN_FAILED, _spy(HOOK_RUN_FAILED), plugin_name="spy"
    )

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

    app_with_executor.state.hooks.register(
        HOOK_RUN_STARTED, _spy(HOOK_RUN_STARTED), plugin_name="spy"
    )
    app_with_executor.state.hooks.register(
        HOOK_RUN_FINISHED, _spy(HOOK_RUN_FINISHED), plugin_name="spy"
    )

    transport = httpx.ASGITransport(app=app_with_executor)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get(
            "/ensemble",
            params={"q": "hello"},
            headers={
                "X-SF-Run-Id": "11111111-1111-1111-1111-111111111111",
                "X-SF-Run-Spec": "hle-claude-single",
            },
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

    app_with_executor.state.hooks.register(
        HOOK_RUN_STARTED, _spy(HOOK_RUN_STARTED), plugin_name="spy"
    )
    app_with_executor.state.hooks.register(
        HOOK_RUN_FAILED, _spy(HOOK_RUN_FAILED), plugin_name="spy"
    )

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

    app_with_executor.state.hooks.register(
        HOOK_RUN_STARTED, _spy(HOOK_RUN_STARTED), plugin_name="spy"
    )

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
