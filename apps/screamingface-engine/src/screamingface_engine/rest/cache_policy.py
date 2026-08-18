"""Converge the run's two cache carriers into ONE effective policy (spec §5.3, D4).

A run can be configured twice — on the WS attach frame, and on the ``GET /`` that starts it — and
the gateway must be told exactly one thing. Everything downstream of this module takes a RESOLVED
policy, which is what lets ``runner/cache.py`` stay a dumb translation: "what does saying nothing
mean?" is answered here, once, and nowhere else.

THE PRECEDENCE RULE — the header wins a genuine disagreement (D4(a)). Attach necessarily happens
first (``_require_subscriber`` refuses to start a run with nothing attached), so the GET is the
LATER, run-scoped statement and last-writer-wins matches causal order. The alternatives were
weighed and rejected: frame-wins inverts that order and will surprise, and treating a conflict as
fatal kills an entire ensemble run over a directive about cost.

**A disagreement is never silent.** The loser is carried out of here on the resolution so the
caller can name it in a warning — a client that stated two things must be able to learn WHICH one
lost, and a resolution that only flagged "there was a conflict" could not tell it.

THE DEFAULT LIVES HERE — silence on both carriers is participation (D1). Deliberately not spread
across the parsers: both of them return ``None`` for "not stated" precisely so that the one place
that turns silence into a decision is this one. Were the header parser to default instead, a
malformed header would shadow a perfectly good frame declaration.
"""

from __future__ import annotations

from dataclasses import dataclass

from url4.streaming.protocol import CachePolicy


def default_policy() -> CachePolicy:
    """The D1 default: a run nobody spoke for participates in the gateway's response cache.

    Built fresh per call rather than shared as a module constant. A pydantic model is mutable, so
    one shared instance handed to every run is state two concurrent runs could contaminate each
    other through — at the one seam where a wrong value costs money silently.
    """
    return CachePolicy(participate=True)


@dataclass(frozen=True)
class Resolution:
    """The run's one policy, plus whatever stating it displaced."""

    effective: CachePolicy
    """What the run actually executes under. Never ``None`` — convergence always decides."""
    overridden: CachePolicy | None = None
    """The frame's declaration, when the header disagreed with it and won; ``None`` otherwise.

    Present so the override can be REPORTED with both halves of the disagreement. It is not an
    error and nothing acts on it beyond saying so."""


def resolve(header: CachePolicy | None, frame: CachePolicy | None) -> Resolution:
    """Reconcile the two carriers' declarations into the run's effective cache policy.

    Args:
        header: What ``Cache-Control`` on the ``GET /`` stated, or ``None`` for "not stated".
        frame: What the WS attach frame declared, or ``None`` for "not stated".

    Returns:
        A :class:`Resolution` whose ``effective`` policy is the header's when it spoke, the
        frame's when only it did, and :func:`default_policy` when neither did. ``overridden``
        names the frame policy the header displaced, and only in that case — one carrier speaking
        into the other's silence is not a disagreement, and reporting it as one would make an
        ordinary per-request directive warn on every run that ever attached quietly.
    """
    if header is None:
        stated = frame if frame is not None else default_policy()
        return Resolution(effective=_degrade_unhonourable_bound(stated))
    # Equality, not identity, and over the WHOLE policy: two carriers that agree on participation
    # while disagreeing on the freshness bound are still two different statements, and the one
    # that applies must be the one the caller is told about.
    overridden = frame if frame is not None and frame != header else None
    return Resolution(effective=_degrade_unhonourable_bound(header), overridden=overridden)


# Whether the gateway can tell url4 how old a cached answer is. FALSE today: aigateway emits no
# `Age` (RFC 9111 §5.1) and no `Cache-Status; ttl=` (RFC 9211 §2.4), and its control grammar is
# closed to `use-cache`, so url4 can neither ask for a bound nor measure one. Raised on PR #507.
#
# FLIPPING THIS TO TRUE is the whole of D11's honouring half: `requires_revalidation` and its
# tests already exist and are correct, they are simply unreachable while this is False.
GATEWAY_REPORTS_AGE = False


def _degrade_unhonourable_bound(policy: CachePolicy) -> CachePolicy:
    """Collapse a freshness bound the gateway cannot honour into an opt-out (spec §3.5).

    WHY collapse here rather than revalidate on the response: with no age reported, EVERY hit
    under a bound is unprovable, so honouring it after the fact means a second gateway call and a
    discarded body on every one — inside `for _ in range(web_tool_max_iterations)`, so a
    four-iteration tool turn becomes eight calls, multiplied again across a fan-out.

    The accidental case is what settles it. D6 chose the standard `Cache-Control` header
    specifically so intermediaries may participate, and `max-age=0` is what a browser reload
    sends. A caller who never thought about caching could otherwise double every gateway call in
    their run by pressing refresh through a forwarding proxy.

    Opting out costs one call and stores nothing, which is the conservative reading of a caller
    who asked for bounded staleness and cannot be given it. It is also observable rather than
    silent: aigateway answers `bypass` with reason `opted_out`.
    """
    if policy.max_age is None or GATEWAY_REPORTS_AGE:
        return policy
    return policy.model_copy(update={"participate": False})


__all__ = ["Resolution", "default_policy", "resolve"]
