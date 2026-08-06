"""What the gateway's response cache did across ONE run — hits, misses, and bypasses by reason
(spec §7 / D7, plan Batch 8).

**WHY counting is not optional.** Caching fails silently in both directions. A hit costs nothing
upstream, so nobody notices the savings; a bypass costs a hit, and the request that caused it
succeeded, so nobody notices the loss either. Per-span `cache_status` answers "what happened to
this call"; only a run-level total answers the question an operator actually asks — *did this run
use the cache, and if not, why not?* — without correlating every span by hand.

**Bypasses BY REASON is the load-bearing one.** The gateway's vocabulary distinguishes
`opted_out` (url4 asked for no cache, and got none — working as designed) from
`unsupported_control` (url4 sent a control key the gateway's closed grammar does not know, and
silently lost EVERY hit — a defect that raises nothing anywhere). Collapsing them into one
"bypasses" number would erase exactly the distinction this telemetry exists to surface.

WHY THIS IS NOT PROMETHEUS. Two reasons, and either alone would settle it:

1. The run mode is a one-shot Job. It has no scrape endpoint and exits when the run does, so a
   counter incremented there is a counter nobody ever reads.
2. `.claude/scripts/check_layering.py` forbids `url4_cloud.runner.*` from importing
   `url4_cloud.metrics` at all — the run mode must not load the serving half.

The run's own telemetry stream is the only channel that exists, and it is also the right one: the
question is about one run, and the answer arrives beside the spans it explains.

INVARIANT — **no counter is labelled by cache key, prompt or credential** (spec §7). Enforced
structurally rather than by review: :meth:`RunCacheCounters.record` accepts a status and a reason
and nothing else, so there is no slot a key could occupy. The gateway's entry key IS parsed, one
seam upstream (:class:`url4_cloud.runner.cache_readback.CacheOutcome`), and deliberately stops
there.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from url4_cloud.runner.cache_readback import CacheStatus

CACHE_HITS = "cache.hits"
CACHE_MISSES = "cache.misses"
CACHE_BYPASSES = "cache.bypasses"
BYPASS_REASON_PREFIX = "cache.bypass."
"""Namespace for the per-reason breakdown, so `cache.bypasses` and its parts read as one family
and a consumer can find the breakdown by prefix without knowing the gateway's vocabulary."""

UNSTATED_REASON = "unstated"
"""The bucket for a bypass that named no reason.

Its own bucket rather than being dropped: the breakdown must always sum to `cache.bypasses`, and
a reader who finds it does not — because some counts silently went nowhere — cannot trust either
number. Spelled without a space so it is usable as an attribute-key suffix; the equivalent notion
for a POLICY renders as :data:`url4_cloud.notices.NOT_STATED`, which is prose, not a key.
"""

OVERFLOW_REASON = "other"
REASON_BUCKET_CAP = 16
"""Ceiling on distinct reason buckets, past which reasons collapse into
:data:`OVERFLOW_REASON` — at most ``REASON_BUCKET_CAP + 1`` buckets in all.

The same cardinality doctrine `url4_cloud.metrics._route_label` applies to a Prometheus label,
for the same reason: the reason is an UPSTREAM FREE STRING, carried verbatim on purpose, and a
gateway that ever embeds a request id in one would otherwise mint a new attribute per call. The
cap costs nothing in practice — the gateway's actual vocabulary is a handful of tokens — and it
collapses rather than drops, so the breakdown still sums to the total it belongs to.
"""

_COUNTED_BYPASS: CacheStatus = "bypass"


@dataclass(slots=True)
class RunCacheCounters:
    """One run's cache tallies. Plain integers, lifted onto the wire by the executor.

    Not a `prometheus_client` object for the layering reason in the module docstring, and not one
    even in spirit: a counter here is scoped to a run and dies with it, which is what makes it
    answerable without any label identifying WHICH run.
    """

    hits: int = 0
    misses: int = 0
    bypasses: int = 0
    _bypass_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def observed(self) -> bool:
        """Whether this run saw any cache outcome at all.

        The gate the executor publishes on. Most runs call no gateway — a static expression, a
        reduce over already-fetched leaves — and an older gateway reports nothing even when one
        is called. Emitting "0 hit, 0 miss, 0 bypass" for those would put a line on every run's
        stream that says only that the feature exists, which trains a reader to skip the line on
        the runs where it says something.
        """
        return bool(self.hits or self.misses or self.bypasses)

    @property
    def bypass_reasons(self) -> Mapping[str, int]:
        """The per-reason breakdown, read-only. Always sums to :attr:`bypasses`."""
        return self._bypass_reasons

    def record(self, status: CacheStatus | None, reason: str | None) -> None:
        """Tally one gateway round trip's reported outcome.

        Args:
            status: What the gateway said, or ``None`` when it said nothing — an older gateway,
                or a path that never reached the cache. ``None`` counts as NOTHING rather than as
                a miss: "not reported" is not "the cache was consulted and had nothing", and
                inventing the second from the first would report a cache interaction that never
                happened.
            reason: The gateway's own word for that status, verbatim. Only a bypass's reason is
                broken out — a miss means the entry simply was not there, which answers nothing a
                reader would ask, while a bypass means the cache was never consulted at all,
                which is precisely the case that needs a why.
        """
        if status == "hit":
            self.hits += 1
        elif status == "miss":
            self.misses += 1
        elif status == _COUNTED_BYPASS:
            self.bypasses += 1
            self._count_reason((reason or "").strip() or UNSTATED_REASON)

    def attributes(self) -> dict[str, str | int | float | bool | None]:
        """The counters as `LogData` attributes: the three totals, plus one entry per reason.

        INVARIANT: every value is an integer count and every key is under `cache.`. That is the
        whole enforcement of spec §7's "no metric labelled by cache key, prompt or credential" —
        the shape admits no other kind of value.
        """
        attributes: dict[str, str | int | float | bool | None] = {
            CACHE_HITS: self.hits,
            CACHE_MISSES: self.misses,
            CACHE_BYPASSES: self.bypasses,
        }
        for reason, count in self._bypass_reasons.items():
            attributes[f"{BYPASS_REASON_PREFIX}{reason}"] = count
        return attributes

    def summary_body(self) -> str:
        """The human-readable half of the summary line.

        The totals are stated here as well as in the attributes on purpose: a reader scanning a
        run's log sees the answer without expanding a structured payload, and the reasons — which
        are the part worth expanding for — stay in the attributes where they can be aggregated.
        """
        return (
            f"gateway response cache: {self.hits} hit, {self.misses} miss, {self.bypasses} bypass"
        )

    def _count_reason(self, reason: str) -> None:
        """Increment ``reason``'s bucket, collapsing into :data:`OVERFLOW_REASON` once the cap is
        reached. An already-known reason always keeps its own bucket, so the cap can never move a
        count that was already being reported separately."""
        if reason not in self._bypass_reasons and len(self._bypass_reasons) >= REASON_BUCKET_CAP:
            reason = OVERFLOW_REASON
        self._bypass_reasons[reason] = self._bypass_reasons.get(reason, 0) + 1


__all__ = [
    "BYPASS_REASON_PREFIX",
    "CACHE_BYPASSES",
    "CACHE_HITS",
    "CACHE_MISSES",
    "OVERFLOW_REASON",
    "REASON_BUCKET_CAP",
    "UNSTATED_REASON",
    "RunCacheCounters",
]
