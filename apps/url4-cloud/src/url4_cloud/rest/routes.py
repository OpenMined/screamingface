"""The run-lifecycle REST surface: mint a capability token, start a run, stop a run.

Implements the transactional-HTTP half of the url4-cloud protocol (spec §4/§5): a token binds
the caller to one topic, ``GET /`` starts the run for that topic (synchronously or async per
RFC 7240 ``Prefer``), and ``DELETE /`` stops it and purges its stream. The streaming half (the
WebSocket the caller attaches to observe the run) lives elsewhere; this module only schedules
work onto it via ``JobRunner``/``EventConsumer`` and enforces that a subscriber is attached
first.
"""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, Response

from url4.streaming.interfaces import (
    EventConsumer,
    JobAlreadyExists,
    JobRunnerAtCapacity,
)
from url4.streaming.protocol import ResultEvent, TerminatedEvent
from url4.streaming.trace import valid_traceparent
from url4_cloud import job_env
from url4_cloud.auth import (
    PROBLEM_MEDIA_TYPE,
    JwtCodec,
    ProblemException,
    VerifiedClaims,
    new_topic,
)
from url4_cloud.config import Settings
from url4_cloud.ports import IdentityAwareJobRunner
from url4_cloud.rest.interest import SubscriberGate

router = APIRouter()

_TERMINAL_PROBLEM: dict[str, tuple[int, str, str]] = {
    "failed": (502, "Bad Gateway", "the run failed"),
    "timed_out": (504, "Gateway Timeout", "the run exceeded its deadline"),
    "stopped": (409, "Conflict", "the run was stopped"),
}


def _default_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Deps:
    """The run-scheduling collaborators a route handler needs, resolved from app state."""

    stream: EventConsumer
    job_runner: IdentityAwareJobRunner
    interest: SubscriberGate
    settings: Settings


def _deps(request: Request) -> _Deps:
    """Resolve ``_Deps`` from app state, or raise 503 if no job runner is configured."""
    state = request.app.state
    job_runner = state.job_runner
    if job_runner is None:
        raise ProblemException(
            status=503,
            title="Service Unavailable",
            detail="run scheduling is not configured (URL4_CLOUD_RUNNER)",
        )
    return _Deps(
        stream=state.stream,
        job_runner=job_runner,
        interest=state.interest,
        settings=state.settings,
    )


@dataclass(frozen=True)
class _Prefer:
    """The parsed RFC 7240 ``Prefer`` header for a start-run request."""

    respond_async: bool
    wait_s: float | None


def _parse_prefer(raw: str) -> _Prefer:
    """Parse an RFC 7240 ``Prefer`` header into ``respond-async``/``wait=<seconds>`` flags.

    Unknown tokens are ignored; a malformed ``wait`` value falls back to ``None`` (the
    default synchronous bound), it never raises.
    """
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
    """Best-effort ``float`` parse: returns ``None`` instead of raising on bad input."""
    try:
        return float(value.strip())
    except ValueError:
        return None


def _require_q(q: str | None) -> str:
    """Return the url4 expression, or raise 400 if the ``q`` query parameter is missing/empty."""
    if not q:
        raise ProblemException(
            status=400,
            title="Bad Request",
            detail="the url4 expression query parameter `q` is required",
        )
    return q


# INVARIANT: a run must never be scheduled before a subscriber is attached to its topic —
# otherwise the run's terminal frame could be produced with nothing observing the stream.
async def _require_subscriber(interest: SubscriberGate, topic: str) -> None:
    """Raise 428 unless a WebSocket subscriber is already attached to ``topic``."""
    if not await interest.has_subscriber(topic):
        raise ProblemException(
            status=428,
            title="Precondition Required",
            detail="attach a WebSocket to the topic before starting the run",
        )


async def _schedule(
    deps: _Deps,
    topic: str,
    url4: str,
    *,
    traceparent: str | None = None,
    profile: str | None = None,
    identity: Mapping[str, str] | None = None,
) -> None:
    """Schedule the run on the job runner, or raise 409 if one already exists for ``topic``.

    Topics are single-shot: both the pre-check and the runner's own ``JobAlreadyExists`` guard
    against a race collapse into the same 409 problem.
    """
    if await deps.job_runner.exists(topic):
        raise ProblemException(status=409, title="Conflict", detail="a run already exists")
    try:
        await deps.job_runner.schedule(
            topic,
            url4,
            deps.settings.job_deadline_s,
            traceparent=traceparent,
            profile=profile,
            identity=identity,
        )
    except JobAlreadyExists as exc:
        raise ProblemException(status=409, title="Conflict", detail="a run already exists") from exc
    except JobRunnerAtCapacity as exc:
        # WHY 503 and not 429: nothing about THIS caller or request was rate-limited — the
        # substrate is saturated, and an identical retry later succeeds. Only a runner that owns a
        # finite local resource (the in-process one) can raise this; a cluster-backed runner lets
        # the scheduler queue instead.
        raise ProblemException(
            status=503,
            title="Service Unavailable",
            detail="the runner is at capacity — retry shortly",
            headers={"Retry-After": "1"},
        ) from exc


def _accepted(topic: str) -> Response:
    """Build the 202 Accepted response, with ``Location``/``Link``/``Preference-Applied``."""
    location = f"/?topic={topic}"
    return Response(
        status_code=202,
        headers={
            "Location": location,
            "Preference-Applied": "respond-async",
            "Link": f'<{location}>; rel="self"',
        },
    )


async def _scan_terminal(
    stream: EventConsumer, topic: str
) -> tuple[TerminatedEvent, ResultEvent | None]:
    """Consume ``topic``'s stream from the start until its terminal frame, unbounded.

    Returns the ``TerminatedEvent`` plus the last ``ResultEvent`` seen, if any. Callers that
    need a time bound wrap this in ``_await_terminal``.
    """
    result: ResultEvent | None = None
    async for event in stream.subscribe(topic, from_sequence=None):
        if isinstance(event, ResultEvent):
            result = event
        elif isinstance(event, TerminatedEvent):
            return event, result
    # AIDEV-NOTE: unreachable in practice — EventConsumer streams always end in a terminal
    # frame (spec §5); this guards against a stream implementation that violates that.
    raise RuntimeError("stream ended before a terminal frame")  # pragma: no cover


async def _await_terminal(
    stream: EventConsumer, topic: str, bound_s: float
) -> tuple[TerminatedEvent, ResultEvent | None] | None:
    """Bound ``_scan_terminal`` by ``bound_s`` seconds; returns ``None`` on timeout."""
    try:
        return await asyncio.wait_for(_scan_terminal(stream, topic), timeout=bound_s)
    except TimeoutError:
        return None


def _result_response(result: ResultEvent | None) -> Response:
    """Build the 200 response body from the run's ``ResultEvent``, or an empty 200 if none."""
    if result is None:
        return Response(status_code=200)
    return Response(
        content=result.data.body,
        media_type=result.data.media_type or "application/json",
        status_code=200,
    )


def _terminal_response(terminated: TerminatedEvent, result: ResultEvent | None) -> Response:
    """Map a terminal frame to its HTTP response: the Result body on success, else a problem."""
    status = terminated.data.status
    if status == "succeeded":
        return _result_response(result)
    # `.get` and not `[...]`: a terminal status added to the protocol but not mapped here would
    # otherwise surface as an unhandled KeyError — a bare 500 with a traceback, rather than a
    # response that still tells the caller the run ended and did not succeed.
    http_status, title, detail = _TERMINAL_PROBLEM.get(
        status,
        (502, "Bad Gateway", f"the run ended with an unhandled terminal status: {status}"),
    )
    raise ProblemException(status=http_status, title=title, detail=detail)


async def _run_sync(deps: _Deps, topic: str, wait_s: float | None) -> Response:
    """Hold the request until the run's terminal frame, or 202-fall-back once the bound elapses.

    The wait is capped at ``settings.sync_max_wait_s`` regardless of a caller-supplied
    ``wait_s`` (RFC 7240 ``Prefer: wait=``), so a client can shorten but never lengthen it.
    """
    cap = deps.settings.sync_max_wait_s
    bound = cap if wait_s is None else min(wait_s, cap)
    outcome = await _await_terminal(deps.stream, topic, bound)
    if outcome is None:
        return _accepted(topic)
    return _terminal_response(outcome[0], outcome[1])


@router.post(
    "/token",
    tags=["Token"],
    summary="Mint a capability token",
    description="Generate a fresh topic and return its HS256 capability JWT (spec §4). No auth.",
)
async def mint_token(request: Request) -> dict[str, str]:
    """Mint a fresh topic and its HS256 capability JWT. Unauthenticated (see route summary)."""
    settings: Settings = request.app.state.settings
    clock = getattr(request.app.state, "clock", _default_clock)
    codec = JwtCodec(secret=settings.jwt_secret, iat_window_s=settings.iat_window_s)
    return {"token": codec.sign(new_topic(), clock())}


def _problem(description: str) -> dict[str, Any]:
    """Build an OpenAPI response entry for an RFC 9457 problem, for use in ``responses=``."""
    return {
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }


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


_PREFER_DESC = (
    "RFC 7240 preference. Omit → synchronous: hold until the terminal frame (bounded by "
    "SYNC_MAX_WAIT), return the Result body. `respond-async` → asynchronous: 202 + Location/Link "
    "now, Result on the WebSocket stream. `wait=<seconds>` caps the synchronous hold."
)


_START_DESC = (
    "Start the run for the token's topic (spec §5).\n\n"
    "Synchronous (default): hold until the terminal frame (bounded by ``SYNC_MAX_WAIT``) and "
    "return the Result body, or an RFC 9457 problem. Asynchronous (``Prefer: respond-async``, or "
    "once the sync bound elapses): return ``202`` + ``Location``/``Link``; the Result arrives on "
    "the WebSocket stream. ``Prefer: wait=<seconds>`` caps the synchronous hold.\n\n"
    "An inbound ``traceparent`` header, when strictly W3C-valid, is forwarded to the run so its "
    "trace is adopted downstream; absent or malformed, nothing is forwarded — a fresh trace is "
    'minted instead (W3C "restart" rule: garbage never propagates).\n\n'
    "The optional ``X-Profile`` header selects which of the resolved caller's stored aigateway "
    "credentials to route through; absent, the gateway's default profile applies.\n\n"
    "The caller's verified identity header (``X-User-Email``) is read off the inbound request and "
    "carried to the run, which renders it onto its aigateway calls. Envoy strips and re-injects it "
    "after re-verifying Cloudflare Access's assertion, so a client cannot forge it. Absent, the "
    "run carries no identity and an aigateway in header mode rejects it."
)


@router.get(
    "/",
    tags=["Execution"],
    summary="Start a url4 run",
    responses=_START_RESPONSES,
    description=_START_DESC,
)
async def start_run(
    request: Request,
    claims: VerifiedClaims,
    q: str | None = None,
    prefer: Annotated[str | None, Header(alias="Prefer", description=_PREFER_DESC)] = None,
    traceparent: Annotated[
        str | None,
        Header(alias="traceparent", description="W3C trace context to adopt for this run."),
    ] = None,
    x_profile: Annotated[
        str | None,
        Header(alias="X-Profile", description="Optional aigateway routing profile label."),
    ] = None,
) -> Response:
    """Require an attached subscriber, then schedule the run for the token's topic, forwarding
    the adopted traceparent and the caller's verified identity; hold for the terminal frame by
    default, or return ``202`` immediately under ``Prefer: respond-async``.

    ``claims: VerifiedClaims`` is a FastAPI dependency, so JWT verification runs before this
    body executes — no code path here touches the topic without an already-verified capability
    token.
    """
    deps = _deps(request)
    topic = str(claims["sub"])
    url4 = _require_q(q)
    await _require_subscriber(deps.interest, topic)
    inbound_traceparent = valid_traceparent(traceparent)
    # WHY read identity off `request` instead of declaring another `Header(...)` param: the mesh
    # gateway owns it, not the caller, so there is no client-facing contract for a signature to
    # document. `or None`: absent identity is None, the same "nothing to forward" every other
    # optional forwarded value uses — one representation rather than an empty mapping meaning it.
    identity = job_env.identity_from_headers(request.headers) or None
    await _schedule(
        deps,
        topic,
        url4,
        traceparent=inbound_traceparent,
        profile=x_profile,
        identity=identity,
    )
    pref = _parse_prefer(prefer or "")
    if pref.respond_async:
        return _accepted(topic)
    return await _run_sync(deps, topic, pref.wait_s)


@router.delete(
    "/",
    tags=["Execution"],
    summary="Stop a run and purge its stream",
    responses=_STOP_RESPONSES,
    description=(
        "Stop the Job for the token's topic and purge its stream (idempotent) → ``204`` (spec §5)."
    ),
)
async def stop_run(request: Request, claims: VerifiedClaims, topic: str | None = None) -> Response:
    """Stop the run for the token's topic and purge its stream; raise 403 on a topic mismatch."""
    deps = _deps(request)
    sub = str(claims["sub"])
    if topic is not None and topic != sub:
        raise ProblemException(
            status=403,
            title="Forbidden",
            detail="the capability token is not authorized for that topic",
        )
    await deps.job_runner.stop(sub)
    # WHY delete and not purge: this is the run's terminal teardown, and purging a broker-backed
    # stream empties it but leaves the stream object, its consumer state and its filestore
    # directory behind — one permanent stream per run, forever. `delete_stream` defaults to
    # `purge` for adapters with nothing broker-side to reclaim, so both modes stay correct.
    await deps.stream.delete_stream(sub)
    return Response(status_code=204)
