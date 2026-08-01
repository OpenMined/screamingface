from __future__ import annotations

from typing import Any, cast

import pytest

import screamingface as sf


def test_client_uses_the_local_engine_by_default_without_opening_network_resources() -> None:
    client = sf.Client()

    assert client.engine_url == "http://127.0.0.1:9108"
    assert client.closed is False


def test_client_normalizes_one_engine_origin() -> None:
    client = sf.Client(engine_url=" https://demo.example:8443/ ")

    assert client.engine_url == "https://demo.example:8443"


def test_client_exposes_automatic_caller_authentication_without_an_auth_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = sf.Client(engine_url="https://engine.example")
    private_client = cast(Any, client)
    calls: list[float] = []
    monkeypatch.setattr(
        private_client._auth,
        "login",
        lambda *, timeout: calls.append(timeout),
    )

    client.login(timeout=12)

    assert calls == [12]
    assert client.authenticated is False
    client.logout()
    client.close()


@pytest.mark.asyncio
async def test_async_client_exposes_the_same_login_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = sf.AsyncClient(engine_url="https://engine.example")
    private_client = cast(Any, client)
    calls: list[float] = []

    async def login(*, timeout: float) -> None:
        calls.append(timeout)

    monkeypatch.setattr(private_client._auth, "login_async", login)
    await client.login(timeout=12)

    assert calls == [12]
    assert client.authenticated is False
    await client.logout()
    await client.aclose()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "engine.example",
        "ftp://engine.example",
        "https://engine.example/api",
        "https://engine.example?q=1",
        "https://engine.example/#fragment",
    ],
)
def test_client_rejects_non_origin_engine_urls(value: str) -> None:
    with pytest.raises(ValueError, match="HTTP\\(S\\) origin"):
        sf.Client(engine_url=value)


def test_client_constructor_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        cast(Any, sf.Client)("https://engine.example")


def test_sync_client_has_deterministic_context_manager_lifetime() -> None:
    with sf.Client(engine_url="http://127.0.0.1:4404") as client:
        assert client.closed is False

    assert client.closed is True


@pytest.mark.asyncio
async def test_async_client_matches_configuration_and_lifetime() -> None:
    async with sf.AsyncClient(engine_url="http://127.0.0.1:4404") as client:
        assert client.engine_url == "http://127.0.0.1:4404"
        assert client.closed is False

    assert client.closed is True


def test_closed_client_cannot_reopen_implicitly() -> None:
    client = sf.Client()
    client.close()

    with pytest.raises(RuntimeError, match="closed"):
        client.evaluate(sf.Model("provider/opus"), benchmark="draco")


def test_sync_manifest_connection_failure_is_typed() -> None:
    client = sf.Client(engine_url="http://127.0.0.1:1")

    with pytest.raises(sf.PlanningError, match="Could not reach"):
        client.evaluate(sf.Model("provider/opus"), benchmark="draco")


@pytest.mark.asyncio
async def test_async_manifest_connection_failure_is_typed() -> None:
    client = sf.AsyncClient(engine_url="http://127.0.0.1:1")

    with pytest.raises(sf.PlanningError, match="Could not reach"):
        await client.evaluate(sf.Model("provider/opus"), benchmark="draco")
    await client.aclose()
    await client.aclose()
    with pytest.raises(RuntimeError, match="closed"):
        await client.evaluate(sf.Model("provider/opus"), benchmark="draco")


def test_close_is_idempotent() -> None:
    client = sf.Client()

    client.close()
    client.close()

    assert client.closed is True


def test_engine_url_rejects_embedded_credentials() -> None:
    with pytest.raises(ValueError, match="without credentials"):
        sf.Client(engine_url="https://user:secret@engine.example")


def test_benchmark_info_is_normalized_and_rejects_invalid_state() -> None:
    benchmark = sf.BenchmarkInfo(
        name=" draco ",
        id=" draco@1 ",
        title=" DRACO ",
        case_count=100,
        primary_metric=" normalized_score ",
        score_direction="maximize",
    )

    assert benchmark.name == "draco"
    assert benchmark.id == "draco@1"
    assert benchmark.title == "DRACO"
    assert benchmark.primary_metric == "normalized_score"

    with pytest.raises(ValueError, match="case_count"):
        sf.BenchmarkInfo("draco", "draco@1", "DRACO", 0, "score", "maximize")
    with pytest.raises(ValueError, match="score_direction"):
        sf.BenchmarkInfo(
            "draco",
            "draco@1",
            "DRACO",
            1,
            "score",
            cast(Any, "sideways"),
        )
