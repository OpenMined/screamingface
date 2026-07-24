"""The ``JobRunner`` port — the stateless run-once job substrate seam (spec §2.2/§3/§5/§9).

The App holds no run state; a run's identity and its single-use ``409`` guard are recomputed from
the token's topic every call via :func:`job_name`. Two adapters implement this port: ``k8s`` for
prod, ``inprocess`` for local mode/dev — both take an injected client/executor factory so tests
run headless.
"""

import hashlib
from typing import Literal, Protocol, runtime_checkable

# INVARIANT: 64 bits of hex — collision-safe over the 62^64 topic space and a valid DNS-1123 label.
_NAME_HASH_LEN = 16

JobStatus = Literal[
    "scheduled",
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "stopped",
    "not_found",
]
"""The run states (spec §3): ``scheduled → running → {succeeded|failed|stopped|timed_out}``, plus
``not_found`` for an unknown/absent topic. Each adapter maps the substrate state it can observe."""

# k8s recommended labels (docs/protocol.md §9) — also stamped on the Runner container.
RUNNER_LABELS = {
    "app.kubernetes.io/name": "url4-runner",
    "app.kubernetes.io/part-of": "url4-cloud",
    "app.kubernetes.io/component": "job",
}


class JobAlreadyExists(Exception):
    """A job for this topic already exists — the stateless single-use guard (spec §5).

    Tokens are single-use: the App maps this to ``409 Conflict`` (docs/protocol.md §7). Raised
    instead of leaking the substrate's native conflict exception, so callers stay adapter-agnostic.
    """


def job_name(topic: str) -> str:
    """Deterministic, DNS-1123-label-safe job name for ``topic`` — ``url4-<hash>``.

    INVARIANT: a pure function of ``topic``. Because the App is stateless, the job's identity (and
    the ``409``-on-repeat check, spec §5) is derived here rather than stored — a name collision on
    ``create`` *is* the "already ran" guard.
    """
    digest = hashlib.sha256(topic.encode("utf-8")).hexdigest()[:_NAME_HASH_LEN]
    return f"url4-{digest}"


@runtime_checkable
class JobRunner(Protocol):
    """Substrate-agnostic run-once job port.

    - ``schedule(topic, url4, deadline_s, traceparent=None, credential=None, profile=None)`` —
      create the run-once job for ``topic`` carrying the url4 expression; returns the
      deterministic :func:`job_name`. Raises :class:`JobAlreadyExists` when a job for ``topic``
      already exists. ``traceparent``, when a strictly-valid W3C string, propagates the caller's
      trace into the run; absent/``None`` lets the run mint its own (W3C restart rule).
      ``credential``/``profile`` forward the caller's aigateway identity into the run (identity
      forwarding, plan §5.3 dec:A — mirrors the ``traceparent`` hop shape); absent/``None``
      leaves the run's connector world deny-by-default. **Never logged** — treat like
      ``AIGATEWAY_SECRET_KEY``.
    - ``stop(topic)`` — delete the job (idempotent — a no-op when it is already gone).
    - ``exists(topic)`` — whether a job for ``topic`` currently exists.
    - ``status(topic)`` — the observed :data:`JobStatus`.
    """

    def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> str: ...
    def stop(self, topic: str) -> None: ...
    def exists(self, topic: str) -> bool: ...
    def status(self, topic: str) -> JobStatus: ...
