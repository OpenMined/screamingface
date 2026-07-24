"""RFC 9457 Problem Details — ``application/problem+json`` rendering (docs/protocol.md §7)."""

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

PROBLEM_MEDIA_TYPE = "application/problem+json"


class Problem(BaseModel):
    """An RFC 9457 problem object; ``None`` members are dropped on the wire."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class ProblemException(Exception):
    """Raise to abort a request with an RFC 9457 problem response."""

    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        type_: str = "about:blank",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.problem = Problem(type=type_, title=title, status=status, detail=detail)
        self.headers = headers
        super().__init__(title)


async def problem_exception_handler(request: Request, exc: Exception) -> Response:
    """Render a :class:`ProblemException` as ``application/problem+json`` (RFC 9457)."""
    # INVARIANT: only registered for ProblemException; re-raise anything else untouched.
    if not isinstance(exc, ProblemException):
        raise exc
    return JSONResponse(
        status_code=exc.problem.status,
        content=exc.problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=exc.headers,
    )


def install_problem_handlers(app: FastAPI) -> None:
    """Wire the RFC 9457 handler additively onto ``app`` (idempotent per exception type)."""
    app.add_exception_handler(ProblemException, problem_exception_handler)
