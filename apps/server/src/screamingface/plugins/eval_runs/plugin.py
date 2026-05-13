"""EvalRunsPlugin — registers models with state and exposes HTTP routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin
from screamingface.plugins.eval_runs.routes import create_router
from screamingface.plugins.eval_runs.store import EvalRunStore

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class EvalRunsPlugin(Plugin):
    name = "eval-runs"
    description = "Persistence + read API for eval/benchmark runs"
    tags: list[str] = ["product:eval"]
    depends: list[str] = ["state"]
    settings_class = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        state = app.state.state_plugin
        state.register_models(
            "eval_runs",
            ["screamingface.plugins.eval_runs.models"],
        )

        app.state.eval_run_store = EvalRunStore()

        router = create_router()
        routes.add_router(self.name, router, prefix="")
