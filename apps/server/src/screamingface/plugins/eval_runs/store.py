"""EvalRunStore — CRUD + eval-runs-specific queries on top of state.BaseStore."""

from __future__ import annotations

from uuid import UUID

from screamingface.plugins.eval_runs.models import EvalRun
from screamingface.plugins.state.store import BaseStore


class EvalRunStore(BaseStore[EvalRun]):
    model = EvalRun

    async def list_summaries(self, *, limit: int = 50, offset: int = 0) -> list[EvalRun]:
        """List runs with favorites first, then most-recent, without prefetching questions."""
        return await EvalRun.all().order_by("-favorite", "-started_at").offset(offset).limit(limit)

    async def get_with_questions(self, run_id: UUID) -> EvalRun | None:
        return await EvalRun.filter(id=run_id).prefetch_related("questions").first()

    async def set_favorite(self, run_id: UUID, favorite: bool) -> EvalRun | None:
        """Toggle a run's favorite flag; returns the updated run or None if missing."""
        run = await EvalRun.get_or_none(id=run_id)
        if run is None:
            return None
        run.favorite = favorite
        await run.save(update_fields=["favorite", "updated_at"])
        return run
