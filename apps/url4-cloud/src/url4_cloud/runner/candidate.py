"""Isolated Candidate Invocation for the ScreamingFace Engine.

The orchestration world owns the public ``/candidate`` route. Each invocation evaluates the
resolved Candidate expression on a separate restricted URL4 node, with only the Benchmark input
bound as ``$input``. Model adapters read the task-local policy through
``current_candidate_model_params``; no mutable world-level policy is shared across concurrent
Cases.
"""

from __future__ import annotations

import contextvars
from collections.abc import Mapping, Set

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.contract import CANDIDATE_ROUTE
from url4_cloud.runner.config import RunnerConfigError

DEFAULT_CANDIDATE_MAX_INVOCATIONS = 10_000

_candidate_model_params: contextvars.ContextVar[Mapping[str, str] | None] = contextvars.ContextVar(
    "url4_cloud_candidate_model_params", default=None
)


def current_candidate_model_params() -> Mapping[str, str] | None:
    """Return the Benchmark-owned policy active for this Candidate task, if any."""

    return _candidate_model_params.get()


class _CandidateInvocation:
    """Apply invocation limits and delegate Candidate URL4 to the restricted world."""

    __slots__ = ("_allowed_policy_params", "_calls", "_max_invocations", "_node")

    def __init__(
        self,
        node: Url4Node,
        *,
        max_invocations: int,
        allowed_policy_params: Set[str],
    ) -> None:
        if max_invocations < 1:
            raise RunnerConfigError("candidate_max_invocations must be at least 1")
        self._node = node
        self._max_invocations = max_invocations
        self._allowed_policy_params = frozenset(allowed_policy_params)
        self._calls = 0

    async def __call__(self, request: Request) -> str:
        # There is deliberately no await between check and increment: Runner handlers share one
        # event loop, so concurrent call sites cannot both claim the same remaining slot.
        if self._calls >= self._max_invocations:
            raise ResolutionError(
                f"Candidate Invocation limit of {self._max_invocations} exceeded",
                code="candidate_invocation_limit",
                permanent=True,
            )
        policy = _candidate_policy(request.params, self._allowed_policy_params)
        self._calls += 1
        token = _candidate_model_params.set(policy)
        try:
            result = await self._node.evaluate(
                request.intent,
                env={"input": request.context or ""},
            )
            return result.text
        finally:
            _candidate_model_params.reset(token)


def install_candidate_invocation(
    orchestration: Url4Node,
    candidate: Url4Node,
    *,
    max_invocations: int,
    allowed_policy_params: Set[str],
) -> None:
    """Install the one Engine-owned Candidate Invocation route on ``orchestration``."""

    orchestration.endpoint(CANDIDATE_ROUTE)(
        _CandidateInvocation(
            candidate,
            max_invocations=max_invocations,
            allowed_policy_params=allowed_policy_params,
        )
    )


def _candidate_policy(
    params: Mapping[str, str],
    allowed_policy_params: Set[str],
) -> dict[str, str]:
    unknown = sorted(set(params) - allowed_policy_params)
    if unknown:
        raise ResolutionError(
            f"unsupported Candidate policy parameter(s) {unknown}",
            code="candidate_policy_invalid",
            permanent=True,
        )
    return dict(params)


__all__ = [
    "DEFAULT_CANDIDATE_MAX_INVOCATIONS",
    "current_candidate_model_params",
    "install_candidate_invocation",
]
