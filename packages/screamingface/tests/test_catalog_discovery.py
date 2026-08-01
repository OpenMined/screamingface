from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

import screamingface as sf
from screamingface import _default_client


def _sync_client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.Client:
    return sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(handler),
    )


def _async_client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.AsyncClient:
    return sf.AsyncClient(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(handler),
    )


def _models(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": [
                {
                    "id": "anthropic/claude-haiku-4-5",
                    "object": "model",
                    "owned_by": "anthropic",
                },
                {
                    "id": "openrouter/openai/gpt-5.5",
                    "object": "model",
                    "owned_by": "openrouter",
                },
            ],
        },
    )


def _benchmarks(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "default": "draco-lite",
            "data": [{"id": "draco-lite", "object": "benchmark"}],
        },
    )


def test_explicit_client_lists_typed_models_and_benchmarks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _models(request)
        if request.url.path == "/v1/benchmarks":
            return _benchmarks(request)
        return httpx.Response(404)

    with _sync_client(handler) as client:
        models = client.models.list()
        benchmarks = client.benchmarks.list()

    assert models == (
        sf.ModelInfo(id="anthropic/claude-haiku-4-5", provider="anthropic"),
        sf.ModelInfo(id="openrouter/openai/gpt-5.5", provider="openrouter"),
    )
    assert benchmarks == ("draco-lite",)


@pytest.mark.asyncio
async def test_async_client_has_the_same_catalogue_interface() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _models(request) if request.url.path == "/v1/models" else _benchmarks(request)

    async with _async_client(handler) as client:
        assert (await client.models.list())[0].id == "anthropic/claude-haiku-4-5"
        assert (await client.benchmarks.list())[0] == "draco-lite"


def test_module_catalogues_delegate_to_the_lazy_default_client(monkeypatch: Any) -> None:
    class Models:
        def list(self) -> tuple[str, ...]:
            return ("model",)

    class Benchmarks:
        def list(self) -> tuple[str, ...]:
            return ("benchmark",)

    class FakeClient:
        models = Models()
        benchmarks = Benchmarks()

    monkeypatch.setattr(_default_client, "_client", FakeClient())

    assert sf.models.list() == ("model",)
    assert sf.benchmarks.list() == ("benchmark",)

    monkeypatch.setattr(_default_client, "_client", None)


@pytest.mark.parametrize(
    ("path", "body", "message"),
    [
        ("/v1/models", {"object": "list", "data": [{"id": ""}]}, "Model id"),
        ("/v1/models", {"object": "wrong", "data": []}, "model catalogue"),
        ("/v1/models", {"object": "list", "data": "wrong"}, "data array"),
        ("/v1/models", {"object": "list", "data": [None]}, "entry must be an object"),
        ("/v1/benchmarks", [], "must be an object"),
        ("/v1/benchmarks", {"object": "wrong", "data": []}, "object must be 'list'"),
        (
            "/v1/benchmarks",
            {"object": "list", "default": "draco", "data": "wrong"},
            "data array",
        ),
        (
            "/v1/benchmarks",
            {"object": "list", "default": "draco", "data": [None]},
            "entry must be an object",
        ),
        (
            "/v1/benchmarks",
            {
                "object": "list",
                "default": "draco",
                "data": [{"id": "draco", "object": "wrong"}],
            },
            "entry object",
        ),
        (
            "/v1/benchmarks",
            {
                "object": "list",
                "default": "draco",
                "data": [
                    {"id": "draco", "object": "benchmark"},
                    {"id": "draco", "object": "benchmark"},
                ],
            },
            "duplicate id",
        ),
        (
            "/v1/benchmarks",
            {
                "object": "list",
                "default": "missing",
                "data": [{"id": "draco", "object": "benchmark"}],
            },
            "default 'missing' is not installed",
        ),
        (
            "/v1/benchmarks",
            {
                "object": "list",
                "data": [{"id": "draco", "object": "benchmark"}],
            },
            "declare default",
        ),
    ],
)
def test_catalogues_reject_malformed_engine_payloads(
    path: str,
    body: object,
    message: str,
) -> None:
    client = _sync_client(
        lambda request: (
            httpx.Response(200, json=body) if request.url.path == path else httpx.Response(404)
        )
    )

    with client, pytest.raises(sf.PlanningError, match=message):
        (client.models if path.endswith("models") else client.benchmarks).list()


def test_catalogue_authentication_failure_is_typed() -> None:
    client = _sync_client(lambda _: httpx.Response(401, json={"detail": "missing"}))

    with client, pytest.raises(sf.AuthenticationError) as exc_info:
        client.models.list()

    assert exc_info.value.status == 401
    assert exc_info.value.code == "authentication_required"


def test_sync_catalogue_connection_failure_is_typed() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = _sync_client(unreachable)

    with client, pytest.raises(sf.EngineUnavailableError) as exc_info:
        client.models.list()

    assert exc_info.value.code == "engine_unreachable"
    assert exc_info.value.permanent is False
    assert exc_info.value.engine_url == "https://engine.example"


@pytest.mark.asyncio
async def test_async_catalogue_connection_failure_is_typed() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with _async_client(unreachable) as client:
        with pytest.raises(sf.EngineUnavailableError) as exc_info:
            await client.benchmarks.list()

    assert exc_info.value.code == "engine_unreachable"
    assert exc_info.value.permanent is False
    assert exc_info.value.engine_url == "https://engine.example"


@pytest.mark.parametrize(
    ("response", "code", "permanent"),
    [
        (httpx.Response(500), "engine_contract_error", False),
        (httpx.Response(200, text="{"), "invalid_catalogue", True),
    ],
)
def test_catalogue_http_and_json_failures_are_typed(
    response: httpx.Response,
    code: str,
    permanent: bool,
) -> None:
    client = _sync_client(lambda _: response)

    with client, pytest.raises(sf.PlanningError) as exc_info:
        client.models.list()

    assert exc_info.value.code == code
    assert exc_info.value.permanent is permanent
