"""The engine observation seam: a passive, pure-data event stream.

The DAG executor emits one small closed set of dataclasses as it runs a graph
— span start/finish, usage, logs, run boundaries — to an injected
:class:`Observer`. This module defines only the *shape* of that stream: it is
a dependency-free leaf (standard library only) so the engine core never gains
a transport or tracing-backend dependency just because an embedder wants to
watch a run. Adapting these events onto any particular wire format or
downstream tracing product is deliberately kept out of this module.

``Observer.on_event`` is synchronous and non-blocking by contract — the
executor calls it inline from its own coroutines, never behind a task or a
queue, so a slow or blocking observer would slow the run itself. An observer
that raises is not caught anywhere in the engine (an embedder bug should be
loud, not swallowed): the exception propagates out of the run exactly like
any other node failure.
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RunStarted:
    """Emitted once, at the very start of a top-level owned-context run."""

    trace_id: str  # 32-hex
    root_span_id: str  # 16-hex
    expression_hash: str


@dataclass(frozen=True, slots=True)
class NodeStarted:
    """Emitted once per node evaluation, right before ``resolve`` is awaited."""

    span_id: str  # 16-hex
    parent_span_id: str | None
    node_kind: str  # type(node).__name__
    detail: str  # best-effort route/url/text, "" if none


@dataclass(frozen=True, slots=True)
class NodeFinished:
    """Emitted once per node evaluation, after ``resolve`` settles."""

    span_id: str
    status: Literal["ok", "error", "cancelled"]
    engine_seq: int
    code: str | None = None
    permanent: bool | None = None


@dataclass(frozen=True, slots=True)
class Log:
    span_id: str | None
    severity: str
    body: str


@dataclass(frozen=True, slots=True)
class Usage:
    span_id: str | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    # WHY a SEPARATE field rather than overwriting `model`: the GenAI semantic conventions
    # distinguish `gen_ai.request.model` (what the caller asked for) from
    # `gen_ai.response.model` (what actually served it), and a gateway is free to resolve an
    # alias to a dated snapshot. `model` above stays the REQUESTED name.
    # INVARIANT: `None` means the provider did not say — never a copy of `model`. Reporting the
    # request as the response makes provider-side model drift undetectable, which is exactly
    # what this field exists to expose.
    response_model: str | None = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Emitted once per model round trip, carrying HOW that call ended.

    Deliberately separate from :class:`Usage` rather than fields on it: `Usage`
    is token accounting, and embedders derive cost frames from it, so a finish
    reason there would put a non-cost fact into cost accounting. A node may emit
    several of these — a tool-calling turn is several round trips against one
    span — so consumers keep the sequence rather than overwriting.

    ``finish_reason`` is the provider's own value, normalized upstream to the
    OpenAI vocabulary (``stop`` | ``length`` | ``content_filter`` |
    ``tool_calls``); ``refusal`` is the provider's refusal text when it sends
    one. Both are optional because not every provider reports either.

    ``cache_status`` / ``cache_reason`` say whether the gateway that answered
    served this round trip from its response cache, and — when it did not —
    its own word for why. They ride HERE rather than on a seam of their own
    because the fact is per-round-trip exactly as ``finish_reason`` is, and an
    adapter reads both off the same response. WHY it must be reported at all: a
    hit costs nothing upstream, so a run that cannot report one bills it as a
    fresh call — an error that HIDES savings and is therefore never noticed.
    ``cache_reason`` is the reporting cache's vocabulary VERBATIM; normalizing
    it here would erase the distinction that makes "I asked for no caching and
    something still cached" an answerable question.
    """

    span_id: str | None
    finish_reason: str | None
    refusal: str | None
    # AIDEV-NOTE: this literal is spelled again on `url4.streaming.protocol.SpanData`, which is
    # where it reaches the wire. Deliberately duplicated rather than shared: this module is the
    # engine's dependency-free observation leaf and the protocol package is the wire contract,
    # and coupling the two to save three tokens would be the worse trade. Change both together.
    cache_status: Literal["hit", "miss", "bypass"] | None = None
    cache_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RunFinished:
    """Emitted once, after the top-level run settles (success or failure)."""

    status: Literal["ok", "error", "cancelled"]
    engine_seq: int


ObservationEvent = (
    RunStarted | NodeStarted | NodeFinished | Log | Usage | ModelResponse | RunFinished
)


@runtime_checkable
class Observer(Protocol):
    """The observation port. Concrete tracing/logging adapters live outside url4."""

    def on_event(self, event: ObservationEvent) -> None:
        """Handle one event. Must be synchronous and non-blocking; may raise."""
        ...


class NullObserver:
    """The no-op observer — never installed by default, available for callers
    that want an explicit ``Observer`` without writing their own no-op."""

    __slots__ = ()

    def on_event(self, event: ObservationEvent) -> None:
        return None


UsageSink = Callable[..., None]  # matches ExecutionContext.report_usage's kwargs:
# (*, provider: str, model: str, input_tokens: int, output_tokens: int,
#  response_model: str | None = None) -> None

_usage_sink: contextvars.ContextVar[UsageSink | None] = contextvars.ContextVar(
    "url4_usage_sink", default=None
)


def current_usage_sink() -> UsageSink | None:
    """The usage sink bound to the currently-resolving node's span, or ``None``
    when no observer is attached / outside a node resolve.

    World adapters (e.g. an AI-gateway connector) call this to report model
    token usage without holding an :class:`~url4.dag.node.ExecutionContext` —
    the executor binds it around each node's ``resolve`` (see
    :meth:`~url4.dag.executor.Executor._eval`), scoped to that node's own
    :class:`asyncio.Task` so concurrent siblings never cross-talk.
    """
    return _usage_sink.get()


ResponseSink = Callable[..., None]  # matches ExecutionContext.report_response's kwargs:
# (*, finish_reason: str | None, refusal: str | None,
#     cache_status: Literal["hit", "miss", "bypass"] | None = None,
#     cache_reason: str | None = None) -> None
# INVARIANT: the two cache kwargs are OPTIONAL. This is a live seam with callers already written
# against it, and an adapter that learns no cache outcome must be able to say nothing rather
# than be forced to invent one.

_response_sink: contextvars.ContextVar[ResponseSink | None] = contextvars.ContextVar(
    "url4_response_sink", default=None
)


def current_response_sink() -> ResponseSink | None:
    """The response sink bound to the currently-resolving node's span, or
    ``None`` when no observer is attached / outside a node resolve.

    The :class:`ModelResponse` counterpart of :func:`current_usage_sink`, bound
    by the same executor hook with the same per-:class:`asyncio.Task` scoping.
    WHY a second sink rather than widening the usage one: a world adapter learns
    a call's finish reason even when the provider reports no usage at all, and
    the two facts have different lifetimes on the wire.
    """
    return _response_sink.get()


@contextlib.contextmanager
def _bind_node_sinks(usage: UsageSink, response: ResponseSink) -> Iterator[None]:
    """Bind both ctx-less sinks to the currently-resolving node, for the duration
    of its own ``resolve`` only.

    Lives here rather than in the executor because the ContextVars are this
    module's private state — the executor should not have to reach into them to
    scope a binding it does not own. Takes the two bound methods rather than an
    ``ExecutionContext`` so this module stays the dependency-free leaf its
    docstring promises (``url4.dag.node`` imports *this*, never the reverse).

    INVARIANT: no cross-talk between concurrent siblings. ContextVar values are
    copied into each :class:`asyncio.Task`'s context at creation, so every
    sibling node sees its own binding, never another's.

    INVARIANT: neither binding outlives the node's resolve — both are reset on
    the success path and the failure path alike.
    """
    usage_token = _usage_sink.set(usage)
    response_token = _response_sink.set(response)
    try:
        yield
    finally:
        _usage_sink.reset(usage_token)
        _response_sink.reset(response_token)


__all__ = [
    "Log",
    "ModelResponse",
    "NodeFinished",
    "NodeStarted",
    "NullObserver",
    "ObservationEvent",
    "Observer",
    "ResponseSink",
    "RunFinished",
    "RunStarted",
    "Usage",
    "UsageSink",
    "current_response_sink",
    "current_usage_sink",
]
