"""Redemption of result claim tickets: serve a spilled result whole, as often as asked.

FEATURE: deliver large results in full instead of cutting them off at 1 MiB (OME-892).

The Runner parks an over-threshold result as a content-addressed file and the terminal
result frame carries only `{artifact_id, size_bytes, sha256}`; this route is where a
client trades that ticket for the complete bytes. `FileResponse` streams from disk
(bounded memory, HTTP Range for resume).

INVARIANT: fetching NEVER deletes. Content addressing means one file can back many claim
tickets (identical results dedupe onto one path), a dropped connection must be retryable,
and a Range request must leave the rest of the file fetchable — delete-on-first-GET broke
all three (review finding on OME-892). Artifacts die by TTL alone: the periodic sweeper in
`app.py` is the single cleanup mechanism.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Request
from fastapi.responses import FileResponse

from screamingface_engine.auth.dependencies import VerifiedClaims
from screamingface_engine.auth.problem import ProblemException

router = APIRouter()


@router.get(
    "/artifacts/{artifact_id}",
    tags=["Runs"],
    summary="Fetch one complete spilled result by its claim ticket",
)
async def get_artifact(
    request: Request,
    claims: VerifiedClaims,
    artifact_id: Annotated[
        str, Path(description="Content address from the result frame's artifact reference.")
    ],
) -> FileResponse:
    # WHY direct attribute access, no getattr fallback: `create_app` always builds the
    # store, so its absence is a wiring bug that must fail loudly, not read as a 404.
    store = request.app.state.artifact_store
    # INVARIANT: `path_for` resolves only lowercase-sha256 ids inside the store root — a
    # traversal id and an unknown id are the same 404, never a file outside the store.
    path = store.path_for(artifact_id)
    if path is None:
        raise ProblemException(
            status=404,
            title="Unknown artifact",
            detail=f"no artifact is stored under {artifact_id!r} — it may have expired "
            "(artifacts are TTL-swept), or, on a multi-pod deployment, the Runner and the "
            "App may not share URL4_CLOUD_ARTIFACTS_DIR (it must name a shared volume)",
        )
    return FileResponse(path, media_type="application/octet-stream")


__all__ = ["router"]
