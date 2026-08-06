"""Local mode owns one explicit loopback AI Gateway connection."""

from fastapi import FastAPI

from url4_cloud.config import Settings
from url4_cloud.connections.aigateway import AigatewayConnections
from url4_cloud.local import LOCAL_AIGATEWAY_BASE_URL, create_local_app


def _app(**kwargs: object) -> FastAPI:
    return create_local_app(Settings(jwt_secret="s" * 32, **kwargs), env={})  # type: ignore[arg-type]


def test_local_app_automatically_wires_the_loopback_aigateway() -> None:
    app = _app()

    assert isinstance(app.state.connections, AigatewayConnections)
    assert str(app.state.connections._client.base_url) == LOCAL_AIGATEWAY_BASE_URL  # noqa: SLF001


def test_local_app_preserves_an_explicit_aigateway_url() -> None:
    app = _app(aigateway_base_url="http://gateway.test:9876")

    assert isinstance(app.state.connections, AigatewayConnections)
    assert str(app.state.connections._client.base_url) == "http://gateway.test:9876"  # noqa: SLF001
