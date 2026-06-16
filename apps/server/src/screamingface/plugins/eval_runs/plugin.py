"""EvalRunsPlugin — registers models with state and exposes HTTP routes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from screamingface.plugin import Plugin
from screamingface.plugins.eval_runs._hook_payloads import (
    HOOK_QUESTION_CHECKED,
    HOOK_RUN_FAILED,
    HOOK_RUN_FINISHED,
    HOOK_RUN_STARTED,
)
from screamingface.plugins.eval_runs._migrations import ensure_favorite_column
from screamingface.plugins.eval_runs.models import EvalQuestion, EvalRun
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

    _question_idx_by_run: dict[str, int]

    def __init__(self) -> None:
        self._question_idx_by_run = {}

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

        async def _on_run_started(**payload) -> None:
            await EvalRun.create(
                id=UUID(payload["run_id"]),
                spec_name=payload["spec_name"],
                url4_expression=payload["url4_expression"],
                started_at=payload["started_at"],
                status="running",
            )
            self._question_idx_by_run[payload["run_id"]] = 0

        async def _on_question_checked(**payload) -> None:
            run_id = payload["run_id"]
            idx = self._question_idx_by_run.get(run_id, 0)
            self._question_idx_by_run[run_id] = idx + 1
            run = await EvalRun.get_or_none(id=UUID(run_id))
            if run is None:
                return  # orphan question (no started hook) — ignore.
            await EvalQuestion.create(
                run=run,
                idx=idx,
                question=payload["question"],
                expected=payload["expected"],
                predicted=payload.get("predicted"),
                correct=payload.get("correct"),
                raw_output=payload.get("raw_output"),
                error=payload.get("error"),
            )

        async def _on_run_finished(**payload) -> None:
            run_id = payload["run_id"]
            run_uuid = UUID(run_id)
            total = await EvalQuestion.filter(run_id=run_uuid).count()
            correct = await EvalQuestion.filter(run_id=run_uuid, correct=True).count()
            accuracy = (correct / total) if total else 0.0
            collected_errors = int(payload.get("collected_errors", 0) or 0)
            update: dict = {
                "status": "done",
                "finished_at": payload["finished_at"],
                "accuracy": accuracy,
                "total_questions": total,
                "correct_questions": correct,
            }
            if collected_errors > 0:
                update["status"] = "degraded"
                update["error"] = (
                    f"{collected_errors} row(s) errored (e.g. a model backend was "
                    f"unavailable); {total} graded."
                )
            await EvalRun.filter(id=run_uuid).update(**update)
            self._question_idx_by_run.pop(run_id, None)

        async def _on_run_failed(**payload) -> None:
            run_id = payload["run_id"]
            await EvalRun.filter(id=UUID(run_id)).update(
                status="failed",
                finished_at=payload["finished_at"],
                error=payload.get("error"),
            )
            self._question_idx_by_run.pop(run_id, None)

        async def _ensure_schema() -> None:
            # Runs after the state plugin's generate_schemas (priority 10) so the
            # eval_run table exists; back-fills the additive `favorite` column on
            # local DBs created before it was introduced.
            if getattr(app.state, "state_ready", False):
                await ensure_favorite_column()

        hooks.register("app.startup", _ensure_schema, plugin_name=self.name, priority=20)
        hooks.register(HOOK_RUN_STARTED, _on_run_started, plugin_name=self.name)
        hooks.register(HOOK_QUESTION_CHECKED, _on_question_checked, plugin_name=self.name)
        hooks.register(HOOK_RUN_FINISHED, _on_run_finished, plugin_name=self.name)
        hooks.register(HOOK_RUN_FAILED, _on_run_failed, plugin_name=self.name)
