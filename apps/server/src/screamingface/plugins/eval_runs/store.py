"""EvalRunStore — CRUD + eval-runs-specific queries on top of state.BaseStore."""

from __future__ import annotations

from uuid import UUID

from screamingface.plugins.eval_runs.models import EvalRun
from screamingface.plugins.state.store import BaseStore


class EvalRunStore(BaseStore[EvalRun]):
    model = EvalRun

    async def list_summaries(self, *, limit: int = 50, offset: int = 0) -> list[EvalRun]:
        """List runs ordered by started_at DESC, without prefetching questions."""
        return await EvalRun.all().order_by("-started_at").offset(offset).limit(limit)

    async def get_with_questions(self, run_id: UUID) -> EvalRun | None:
        return (
            await EvalRun.filter(id=run_id)
            .prefetch_related("questions")
            .first()
        )
