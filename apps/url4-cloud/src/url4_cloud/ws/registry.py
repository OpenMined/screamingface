"""In-process, per-topic WebSocket session state: how many connections are attached, what cache
policy the first of them declared, and where to reach them with a notice.

All three live on one record deliberately. A declaration is only load-bearing between the first
attach and the moment the run is scheduled — ``_require_subscriber`` refuses to schedule a run
with nothing attached, so that window is entirely contained inside "this topic has a subscriber",
and the runner captures the policy at schedule time. Binding the declaration's lifetime to the
subscriber count therefore costs nothing that can affect a run, and buys a store bounded by live
connections instead of one that grows by a row per topic the process has ever seen.

The same invariant is what makes the notice channel deliverable rather than best-effort: the REST
route can only override a frame's declaration on a request that already passed the 428 gate, so a
socket for the topic is attached, in THIS process, at exactly that moment. The App never publishes
to the broker — it schedules runs and reads their log — so routing a notice through the attached
connection is the only path that does not change that posture.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from url4.streaming.protocol import CachePolicy, OutboundFrame

Notify = Callable[[OutboundFrame], None]
"""How one live connection accepts an out-of-band frame. Synchronous and non-blocking by
contract: it is called from a request handler, so it hands the frame to that connection's own
outbound queue and returns — it must never await the socket."""


@dataclass
class _Session:
    """One topic's WS session: live connections, the cache intent they declared, and their sinks."""

    subscribers: int = 0
    cache: CachePolicy | None = None
    cache_declared: bool = False
    """Whether ANY attach has spoken yet. Distinct from ``cache is None`` on purpose: an attach
    frame carrying no policy still declares — it fixes the run under the default — so without this
    flag a later attach could retroactively opt out a run that had already started."""
    notifiers: list[Notify] = field(default_factory=list)
    """One sink per live connection on this topic. A list and not a single slot because two
    sockets may legitimately observe one run, and a notice about the run belongs to both."""


class ConnectionRegistry:
    """Tracks each topic's live WS connections and its first-attach cache declaration.

    Counts, rather than sets of connection ids, so concurrent connections on the same topic are
    supported without the endpoint having to hand back a token.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}

    def add(self, topic: str) -> None:
        self._sessions.setdefault(topic, _Session()).subscribers += 1

    def remove(self, topic: str) -> None:
        session = self._sessions.get(topic)
        if session is None:
            return
        session.subscribers -= 1
        if session.subscribers <= 0:
            del self._sessions[topic]

    async def has_subscriber(self, topic: str) -> bool:
        session = self._sessions.get(topic)
        return session is not None and session.subscribers > 0

    def declare_cache_policy(self, topic: str, policy: CachePolicy | None) -> bool:
        """Record ``policy`` as ``topic``'s cache intent — FIRST ATTACH WINS (spec §5.2).

        Args:
            topic: The run's topic.
            policy: What this attach frame declared; ``None`` when it declared nothing.

        Returns:
            ``True`` when the topic's standing intent now equals ``policy`` — either because this
            call recorded it, or because the call merely restated what was already recorded (an
            ordinary reconnect re-sending its frame, which must not be reported as anything).
            ``False`` when an intent was already recorded and this one DIFFERS: the standing one
            is left untouched and the caller is expected to say so.

        A run's aigateway calls may already have executed under the recorded intent, so letting a
        re-attach change it would make the run's cache behaviour unreproducible — the reason the
        answer is "ignored and reported" rather than "last writer wins".
        """
        session = self._sessions.setdefault(topic, _Session())
        if session.cache_declared:
            return session.cache == policy
        session.cache_declared = True
        session.cache = policy
        return True

    def cache_policy_for(self, topic: str) -> CachePolicy | None:
        """``topic``'s declared cache intent, or ``None`` if nothing was declared for it.

        ``None`` is deliberately the answer to both "no attach has spoken" and "an attach declared
        nothing": neither states an intent, and both resolve to the default at convergence. What
        the two must NOT be confused with is an explicit opt-out, and that is a policy, not
        ``None``.
        """
        session = self._sessions.get(topic)
        return session.cache if session is not None else None

    def add_notifier(self, topic: str, notify: Notify) -> None:
        """Register one connection's sink for out-of-band frames on ``topic``."""
        self._sessions.setdefault(topic, _Session()).notifiers.append(notify)

    def remove_notifier(self, topic: str, notify: Notify) -> None:
        """Drop a sink registered by :meth:`add_notifier`; a stale one is not an error.

        Idempotent on purpose: the connection that registered it unregisters in a ``finally``,
        which also runs on the path where the last ``remove`` already discarded the whole session.
        """
        session = self._sessions.get(topic)
        if session is not None and notify in session.notifiers:
            session.notifiers.remove(notify)

    def notify(self, topic: str, frame: OutboundFrame) -> None:
        """Offer ``frame`` to every connection attached to ``topic``.

        Best-effort by design, and silent about a topic nobody is listening to: a notice explains
        something about a request that has ALREADY been accepted, so failing the request because
        the explanation could not be delivered would trade a real answer for a footnote. The sinks
        are copied before iterating — a sink is free to drop the frame, and nothing here should
        depend on the list surviving the call.
        """
        session = self._sessions.get(topic)
        if session is None:
            return
        for notify in list(session.notifiers):
            notify(frame)
