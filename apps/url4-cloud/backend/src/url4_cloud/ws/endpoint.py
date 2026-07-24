"""``GET /ws`` — the CloudEvents WebSocket binding (subprotocol ``cloudevents.json``; §6, §8).

A JWT capability *ticket* (query param — browsers cannot set WS request headers) selects
the topic; the connection is registered as live interest (so the REST ``428`` guard opens, spec §4)
and the :func:`run_bridge` engine streams the topic's ``Bus`` frames until the client disconnects.
Deps come off ``websocket.app.state`` (bus / registry / job_runner / settings / clock) so the
endpoint runs headless with injected fakes.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket

from url4_cloud.auth import AuthError, JwtCodec
from url4_cloud.config import Settings
from url4_cloud.jobs.port import JobRunner
from url4_cloud.ws.bridge import run_bridge
from url4_cloud.ws.registry import ConnectionRegistry
from url4_cloud_nats import Bus

router = APIRouter()

_SUBPROTOCOL = "cloudevents.json"
_POLICY_VIOLATION = 1008  # invalid/missing ticket (RFC 6455 close code)
_INTERNAL_ERROR = 1011  # no bus configured


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _ticket_topic(websocket: WebSocket, ticket: str | None) -> str | None:
    if ticket is None:
        return None
    settings: Settings = websocket.app.state.settings
    clock = getattr(websocket.app.state, "clock", _default_clock)
    codec = JwtCodec(secret=settings.jwt_secret, iat_window_s=settings.iat_window_s)
    try:
        return str(codec.verify(ticket, clock())["sub"])
    except AuthError:
        return None


async def _accept(websocket: WebSocket) -> None:
    # CloudEvents WS binding: echo the subprotocol when offered (docs/protocol.md §8).
    offered = websocket.scope.get("subprotocols") or []
    subprotocol = _SUBPROTOCOL if _SUBPROTOCOL in offered else None
    await websocket.accept(subprotocol=subprotocol)


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, ticket: str | None = None) -> None:
    """Verify the ticket, register interest, then bridge the topic's stream (spec §6)."""
    topic = _ticket_topic(websocket, ticket)
    if topic is None:
        await websocket.close(code=_POLICY_VIOLATION)
        return
    bus: Bus | None = websocket.app.state.bus
    if bus is None:
        await websocket.close(code=_INTERNAL_ERROR)
        return
    registry: ConnectionRegistry = websocket.app.state.registry
    job_runner: JobRunner | None = websocket.app.state.job_runner
    clock = getattr(websocket.app.state, "clock", _default_clock)
    heartbeat_s: float = websocket.app.state.settings.ws_heartbeat_s
    registry.add(topic)
    try:
        await _accept(websocket)
        await run_bridge(
            websocket, bus, topic, job_runner=job_runner, clock=clock, heartbeat_s=heartbeat_s
        )
    finally:
        registry.remove(topic)
