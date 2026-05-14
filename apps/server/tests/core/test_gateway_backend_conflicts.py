from __future__ import annotations

from fastapi import FastAPI
from starlette.routing import Route

from screamingface.core.config import AppConfig, ServerConfig
from screamingface.core.registry import PluginRegistry
from screamingface.core.routes import RouteRegistry
from screamingface.plugin import Plugin
from screamingface.plugins.aigw_claude_backend.plugin import AigwClaudeBackendPlugin
from screamingface.plugins.aigw_codex_backend.plugin import AigwCodexBackendPlugin
from screamingface.plugins.claude_backend_api.plugin import ClaudeBackendApiPlugin
from screamingface.plugins.codex_backend_api.plugin import CodexBackendApiPlugin


class _DependencyPlugin(Plugin):
    def __init__(self, name: str) -> None:
        self.name = name


def _registry_with_deps() -> PluginRegistry:
    registry = PluginRegistry()
    for name in {"llm-base", "backend-api-base", "aigw-base"}:
        registry._active[name] = _DependencyPlugin(name)
    return registry


def _activate_pair(first: Plugin, second: Plugin) -> tuple[PluginRegistry, FastAPI]:
    app = FastAPI()
    app.state.config = AppConfig(server=ServerConfig(host="127.0.0.1"))
    routes = RouteRegistry(app)
    registry = _registry_with_deps()

    registry.activate(first, app=app, hooks=None, classes=None, routes=routes)
    registry.activate(second, app=app, hooks=None, classes=None, routes=routes)
    return registry, app


def _path_count(app: FastAPI, path: str) -> int:
    return sum(1 for route in app.routes if isinstance(route, Route) and route.path == path)


def test_codex_direct_and_gateway_conflict_in_both_activation_orders() -> None:
    first_registry, first_app = _activate_pair(CodexBackendApiPlugin(), AigwCodexBackendPlugin())
    second_registry, second_app = _activate_pair(AigwCodexBackendPlugin(), CodexBackendApiPlugin())

    assert "codex-backend-api" in first_registry.active_plugins
    assert "aigw-codex-backend" not in first_registry.active_plugins
    assert _path_count(first_app, "/codex/health") == 1
    assert "aigw-codex-backend" in second_registry.active_plugins
    assert "codex-backend-api" not in second_registry.active_plugins
    assert _path_count(second_app, "/codex/health") == 1


def test_claude_direct_and_gateway_conflict_in_both_activation_orders() -> None:
    first_registry, first_app = _activate_pair(ClaudeBackendApiPlugin(), AigwClaudeBackendPlugin())
    second_registry, second_app = _activate_pair(
        AigwClaudeBackendPlugin(), ClaudeBackendApiPlugin()
    )

    assert "claude-backend-api" in first_registry.active_plugins
    assert "aigw-claude-backend" not in first_registry.active_plugins
    assert _path_count(first_app, "/claude/health") == 1
    assert "aigw-claude-backend" in second_registry.active_plugins
    assert "claude-backend-api" not in second_registry.active_plugins
    assert _path_count(second_app, "/claude/health") == 1
