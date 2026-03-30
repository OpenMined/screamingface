"""REST API routes for the session service."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from screamingface.core.session import (
    CanonicalMessage,
    SessionMetadata,
    SessionStore,
)


def create_router(store: SessionStore) -> APIRouter:
    router = APIRouter(tags=["session-service"])

    @router.post("/sessions", response_model=None, operation_id="create_session")
    async def create_session(
        title: str | None = None,
        provider: str = "",
    ) -> JSONResponse:
        metadata = SessionMetadata(
            title=title,
            provider=provider,
        )
        store.create(metadata)
        return JSONResponse(
            content=metadata.model_dump(mode="json"),
            status_code=201,
        )

    @router.get("/sessions", response_model=None, operation_id="list_sessions")
    async def list_sessions(
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        sessions = store.list_sessions(limit=limit, offset=offset)
        return JSONResponse(
            content=[s.model_dump(mode="json") for s in sessions],
        )

    @router.get(
        "/sessions/{session_id}",
        response_model=None,
        operation_id="get_session",
    )
    async def get_session(session_id: str) -> JSONResponse:
        try:
            metadata = store.load_metadata(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return JSONResponse(content=metadata.model_dump(mode="json"))

    @router.get(
        "/sessions/{session_id}/messages",
        response_model=None,
        operation_id="get_session_messages",
    )
    async def get_session_messages(session_id: str) -> JSONResponse:
        try:
            messages = store.load_messages(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return JSONResponse(
            content=[m.model_dump(mode="json") for m in messages],
        )

    @router.post(
        "/sessions/{session_id}/messages",
        response_model=None,
        operation_id="append_session_message",
    )
    async def append_session_message(
        session_id: str,
        message: CanonicalMessage,
    ) -> JSONResponse:
        try:
            store.append_message(session_id, message)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return JSONResponse(content={"status": "ok"}, status_code=201)

    @router.delete(
        "/sessions/{session_id}",
        response_model=None,
        operation_id="delete_session",
    )
    async def delete_session(session_id: str) -> JSONResponse:
        try:
            store.delete(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return JSONResponse(content={"status": "deleted"})

    return router
