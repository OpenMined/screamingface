"""HTTP routes for eval_runs — list and detail."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from screamingface.plugins.eval_runs.schemas import (
    EvalQuestionOut,
    EvalRunOut,
    EvalRunPatchIn,
    EvalRunSummaryOut,
)

__all__ = ["create_router"]


def create_router() -> APIRouter:
    router = APIRouter(tags=["eval-runs"])

    @router.get(
        "/eval_runs",
        response_model=list[EvalRunSummaryOut],
        operation_id="eval_runs_list",
    )
    async def list_runs(
        request: Request, limit: int = 50, offset: int = 0
    ) -> list[EvalRunSummaryOut]:
        store = request.app.state.eval_run_store
        runs = await store.list_summaries(limit=limit, offset=offset)
        return [EvalRunSummaryOut.model_validate(r) for r in runs]

    @router.get(
        "/eval_runs/{run_id}",
        response_model=EvalRunOut,
        operation_id="eval_runs_get",
    )
    async def get_run(request: Request, run_id: UUID) -> EvalRunOut:
        store = request.app.state.eval_run_store
        run = await store.get_with_questions(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        questions = sorted(run.questions, key=lambda q: q.idx)
        summary = EvalRunSummaryOut.model_validate(run).model_dump()
        return EvalRunOut(
            **summary,
            questions=[EvalQuestionOut.model_validate(q) for q in questions],
        )

    @router.patch(
        "/eval_runs/{run_id}",
        response_model=EvalRunSummaryOut,
        operation_id="eval_runs_patch",
    )
    async def patch_run(request: Request, run_id: UUID, body: EvalRunPatchIn) -> EvalRunSummaryOut:
        store = request.app.state.eval_run_store
        fields = body.model_dump(exclude_unset=True)
        run = await store.patch(run_id, **fields) if fields else await store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return EvalRunSummaryOut.model_validate(run)

    @router.delete(
        "/eval_runs/{run_id}",
        status_code=204,
        operation_id="eval_runs_delete",
    )
    async def delete_run(request: Request, run_id: UUID) -> Response:
        store = request.app.state.eval_run_store
        if not await store.delete(run_id):
            raise HTTPException(status_code=404, detail="run not found")
        return Response(status_code=204)

    return router
