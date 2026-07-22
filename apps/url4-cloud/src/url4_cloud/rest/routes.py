"""REST control plane — ``POST /token`` · ``GET /?q=`` · ``DELETE /`` (spec §5; protocol.md §7).

Deps (bus, job_runner, subscriber-gate, settings, clock) are read from ``request.app.state`` so the
plane runs headless with injected fakes. Sync vs async is selected with RFC 7240 ``Prefer``; the
sync hold is bounded by ``min(wait, SYNC_MAX_WAIT)`` and degrades to ``202`` past the bound; the
terminal frame's status maps to the §5 outcome table. Every error is an RFC 9457 problem+json.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, Response

from url4_cloud.auth import (
    PROBLEM_MEDIA_TYPE,
    JwtCodec,
    ProblemException,
    VerifiedClaims,
    new_topic,
)
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobAlreadyExists, JobRunner
from url4_cloud.rest.interest import SubscriberGate
from url4_cloud_nats import Bus
from url4_streaming_protocol import ResultEvent, TerminatedEvent

router = APIRouter()

# INVARIANT: non-``succeeded`` terminal status → (HTTP status, title, detail) per spec §5. The App
# is a gateway to the Job: a run failure is ``502``, the 16 h deadline is ``504``, a ``DELETE``-stop
# is ``409``. ``succeeded`` is not here — it returns the Result body, not a problem.
_TERMINAL_PROBLEM: dict[str, tuple[int, str, str]] = {
    "failed": (502, "Bad Gateway", "the run failed"),
    "timed_out": (504, "Gateway Timeout", "the run exceeded its deadline"),
    "stopped": (409, "Conflict", "the run was stopped"),
}


def _default_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Deps:
    bus: Bus
    job_runner: JobRunner
    interest: SubscriberGate
    settings: Settings


def _deps(request: Request) -> _Deps:
    state = request.app.state
    return _Deps(
        bus=state.bus,
        job_runner=state.job_runner,
        interest=state.interest,
        settings=state.settings,
    )


@dataclass(frozen=True)
class _Prefer:
    respond_async: bool
    wait_s: float | None


def _parse_prefer(raw: str) -> _Prefer:
    """Parse an RFC 7240 ``Prefer`` header for ``respond-async`` and ``wait=<s>``."""
    respond_async = False
    wait_s: float | None = None
    for token in raw.split(","):
        name, _, value = token.partition("=")
        key = name.strip().lower()
        if key == "respond-async":
            respond_async = True
        elif key == "wait":
            wait_s = _as_float(value)
    return _Prefer(respond_async=respond_async, wait_s=wait_s)


def _as_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None


def _require_q(q: str | None) -> str:
    if not q:
        raise ProblemException(
            status=400,
            title="Bad Request",
            detail="the url4 expression query parameter `q` is required",
        )
    return q


async def _require_subscriber(interest: SubscriberGate, topic: str) -> None:
    # WHY: spec §4 — no run begins with nobody listening; the WS must be attached first (428).
    if not await interest.has_subscriber(topic):
        raise ProblemException(
            status=428,
            title="Precondition Required",
            detail="attach a WebSocket to the topic before starting the run",
        )


def _schedule(deps: _Deps, topic: str, url4: str) -> None:
    # INVARIANT: single-use — the deterministic Job name is the stateless "already ran" guard (§5).
    if deps.job_runner.exists(topic):
        raise ProblemException(status=409, title="Conflict", detail="a run already exists")
    try:
        deps.job_runner.schedule(topic, url4, deps.settings.job_deadline_s)
    except JobAlreadyExists as exc:
        raise ProblemException(status=409, title="Conflict", detail="a run already exists") from exc


def _accepted(topic: str) -> Response:
    """A ``202`` async handle: RFC 7240 ``Preference-Applied`` + RFC 8288 ``Link``/``Location``."""
    location = f"/?topic={topic}"
    return Response(
        status_code=202,
        headers={
            "Location": location,
            "Preference-Applied": "respond-async",
            "Link": f'<{location}>; rel="self"',
        },
    )


async def _scan_terminal(bus: Bus, topic: str) -> tuple[TerminatedEvent, ResultEvent | None]:
    """Consume the topic from the start until the terminal frame; keep the last Result seen."""
    result: ResultEvent | None = None
    async for event in bus.subscribe(topic, from_sequence=None):
        if isinstance(event, ResultEvent):
            result = event
        elif isinstance(event, TerminatedEvent):
            return event, result
    raise RuntimeError("stream ended before a terminal frame")  # pragma: no cover


async def _await_terminal(
    bus: Bus, topic: str, bound_s: float
) -> tuple[TerminatedEvent, ResultEvent | None] | None:
    """The terminal frame within ``bound_s`` seconds, or ``None`` when the bound elapses first."""
    try:
        return await asyncio.wait_for(_scan_terminal(bus, topic), timeout=bound_s)
    except TimeoutError:
        return None


def _result_response(result: ResultEvent | None) -> Response:
    if result is None:
        return Response(status_code=200)
    return Response(
        content=result.data.body,
        media_type=result.data.media_type or "application/json",
        status_code=200,
    )


def _terminal_response(terminated: TerminatedEvent, result: ResultEvent | None) -> Response:
    status = terminated.data.status
    if status == "succeeded":
        return _result_response(result)
    http_status, title, detail = _TERMINAL_PROBLEM[status]
    raise ProblemException(status=http_status, title=title, detail=detail)


async def _run_sync(deps: _Deps, topic: str, wait_s: float | None) -> Response:
    cap = deps.settings.sync_max_wait_s
    bound = cap if wait_s is None else min(wait_s, cap)
    outcome = await _await_terminal(deps.bus, topic, bound)
    if outcome is None:
        return _accepted(topic)  # degrade to async past the bound (spec §5, RFC 7240)
    return _terminal_response(outcome[0], outcome[1])


@router.post("/token", tags=["Token"], summary="Mint a capability token")
async def mint_token(request: Request) -> dict[str, str]:
    """Generate a fresh topic and return its HS256 capability JWT (spec §4). No auth."""
    settings: Settings = request.app.state.settings
    clock = getattr(request.app.state, "clock", _default_clock)
    codec = JwtCodec(secret=settings.jwt_secret, iat_window_s=settings.iat_window_s)
    return {"token": codec.sign(new_topic(), clock())}


def _problem(description: str) -> dict[str, Any]:
    # WHY: a raw problem+json content with the RFC 9457 Problem $ref — NOT FastAPI ``model=`` (which
    # forces an application/json variant); Problem is registered in components by the OpenAPI
    # customizer so the ref resolves (OME-552, spec §7).
    return {
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }


# INVARIANT: these OpenAPI responses mirror the runtime §5 outcomes — 200 Result / 202 async handle
# / RFC 9457 problems. The handlers still return a bare Response; this is documentation only.
_START_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"description": "The run succeeded — the Result body."},
    202: {
        "description": "Accepted — async (Prefer: respond-async, or the sync bound elapsed).",
        "headers": {
            "Location": {"schema": {"type": "string"}, "description": "The run handle."},
            "Link": {"schema": {"type": "string"}, "description": "RFC 8288 self link to the run."},
            "Preference-Applied": {
                "schema": {"type": "string"},
                "description": "RFC 7240 applied preference.",
            },
        },
    },
    400: _problem("The url4 expression query parameter `q` is required."),
    409: _problem("A run already exists for this topic (single-shot)."),
    428: _problem("Attach a WebSocket to the topic before starting the run."),
    502: _problem("The run failed."),
    504: _problem("The run exceeded its 16 h deadline."),
}
_STOP_RESPONSES: dict[int | str, dict[str, Any]] = {
    204: {"description": "Stopped and the stream purged (idempotent)."},
    403: _problem("The capability token is not authorized for that topic."),
}


@router.get("/", tags=["Execution"], summary="Start a url4 run", responses=_START_RESPONSES)
async def start_run(request: Request, claims: VerifiedClaims, q: str | None = None) -> Response:
    """Schedule the run for the token's topic; hold for the terminal unless ``respond-async``."""
    deps = _deps(request)
    topic = str(claims["sub"])
    url4 = _require_q(q)
    await _require_subscriber(deps.interest, topic)
    _schedule(deps, topic, url4)
    prefer = _parse_prefer(request.headers.get("Prefer", ""))
    if prefer.respond_async:
        return _accepted(topic)
    return await _run_sync(deps, topic, prefer.wait_s)


@router.delete(
    "/", tags=["Execution"], summary="Stop a run and purge its stream", responses=_STOP_RESPONSES
)
async def stop_run(request: Request, claims: VerifiedClaims, topic: str | None = None) -> Response:
    """Stop the Job for the token's topic and purge its stream (idempotent) → ``204`` (spec §5)."""
    deps = _deps(request)
    sub = str(claims["sub"])
    if topic is not None and topic != sub:
        raise ProblemException(
            status=403,
            title="Forbidden",
            detail="the capability token is not authorized for that topic",
        )
    deps.job_runner.stop(sub)
    await deps.bus.purge(sub)
    return Response(status_code=204)
