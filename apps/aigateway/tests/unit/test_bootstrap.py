from typing import Any

from fastapi.testclient import TestClient

from aigateway.core.auth.middleware import ANONYMOUS_ACCOUNT_ID
from aigateway.core.plugin_base import ModelEntry, ProviderPluginBase
from tests.conftest import _prepare_sqlite_db


def _configure_app_db(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite://{tmp_path / 'aigateway.sqlite3'}"
    monkeypatch.setenv("AIGATEWAY_DATABASE_URL", database_url)
    monkeypatch.setenv("AIGATEWAY_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("AIGATEWAY_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("AIGATEWAY_PROVISIONING_TOKEN", "p" * 32)
    _prepare_sqlite_db(database_url)


def _auth_header(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


class _BootstrapSpyPlugin(ProviderPluginBase):
    custom_llm_provider = "spy"

    def __init__(self, bootstrap_mock) -> None:
        self.bootstrap_mock = bootstrap_mock

    def register_models(self) -> list[ModelEntry]:
        return []

    async def bootstrap_profiles(self, **kwargs: Any) -> None:
        await self.bootstrap_mock(**kwargs)


def _install_bootstrap_spy(monkeypatch, main_module, bootstrap_mock) -> None:
    def _load_plugins(registry) -> None:
        registry.register(_BootstrapSpyPlugin(bootstrap_mock))

    monkeypatch.setattr(main_module, "load_plugins", _load_plugins)


def test_lifespan_skips_bootstrap_by_default(monkeypatch, tmp_path) -> None:
    """When AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE is unset, _lifespan does not call bootstrap."""
    from unittest.mock import AsyncMock

    monkeypatch.delenv("AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE", raising=False)
    _configure_app_db(monkeypatch, tmp_path)

    from aigateway import main as main_module

    mock_bootstrap = AsyncMock()
    _install_bootstrap_spy(monkeypatch, main_module, mock_bootstrap)

    app = main_module.create_app()
    with TestClient(app) as client:
        resp = client.get("/v1/auth/profiles", headers=_auth_header(client))
        assert resp.status_code == 200
        assert resp.json() == {"profiles": []}

    assert mock_bootstrap.call_count == 0


def test_lifespan_runs_bootstrap_when_env_set(monkeypatch, tmp_path) -> None:
    """When AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE=1, _lifespan calls bootstrap."""
    from unittest.mock import AsyncMock

    monkeypatch.setenv("AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE", "1")
    _configure_app_db(monkeypatch, tmp_path)

    from aigateway import main as main_module

    mock_bootstrap = AsyncMock()
    _install_bootstrap_spy(monkeypatch, main_module, mock_bootstrap)

    app = main_module.create_app()
    with TestClient(app) as client:
        client.get("/v1/auth/profiles", headers=_auth_header(client))

    assert mock_bootstrap.call_count == 1
    assert mock_bootstrap.call_args.kwargs["account_id"]


def test_lifespan_bootstraps_disabled_auth_under_anonymous_account(monkeypatch, tmp_path) -> None:
    from unittest.mock import AsyncMock

    monkeypatch.setenv("AIGATEWAY_AUTH_ENABLED", "0")
    monkeypatch.setenv("AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE", "1")
    _configure_app_db(monkeypatch, tmp_path)

    from aigateway import main as main_module

    mock_bootstrap = AsyncMock()
    _install_bootstrap_spy(monkeypatch, main_module, mock_bootstrap)

    app = main_module.create_app()
    with TestClient(
        app,
        base_url="http://127.0.0.1:9105",
        client=("127.0.0.1", 50000),
    ) as client:
        resp = client.get("/v1/auth/me")
        assert resp.status_code == 200

    assert mock_bootstrap.call_count == 1
    assert mock_bootstrap.call_args.kwargs["account_id"] == str(ANONYMOUS_ACCOUNT_ID)
