from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from screamingface.plugins.aigw_base.plugin_base import _assert_loopback_sf_bind


def _app_with_host(host: str) -> FastAPI:
    app = FastAPI()
    app.state.config = SimpleNamespace(server=SimpleNamespace(host=host))
    return app


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_gateway_backed_backend_allows_loopback_sf_bind(host: str) -> None:
    _assert_loopback_sf_bind(_app_with_host(host))


def test_gateway_backed_backend_rejects_lan_sf_bind() -> None:
    with pytest.raises(RuntimeError, match="loopback"):
        _assert_loopback_sf_bind(_app_with_host("0.0.0.0"))


def test_gateway_backed_backend_allows_explicit_lan_override(monkeypatch) -> None:
    monkeypatch.setenv("SF_AIGW_ALLOW_LAN", "1")

    _assert_loopback_sf_bind(_app_with_host("0.0.0.0"))
