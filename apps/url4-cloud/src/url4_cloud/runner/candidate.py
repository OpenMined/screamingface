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
from url4_cloud.benchmarks.contract import CANDIDATE_ROUTE, encode_candidate_invocation
from url4_cloud.runner.config import RunnerConfigError

DEFAULT_CANDIDATE_MAX_INVOCATIONS = 10_000

_candidate_model_params: contextvars.ContextVar[Mapping[str, str] | None] = contextvars.ContextVar(
    "url4_cloud_candidate_model_params", default=None
)
_candidate_finish_reasons: contextvars.ContextVar[list[str | None] | None] = contextvars.ContextVar(
    "url4_cloud_candidate_finish_reasons", default=None
)


def current_candidate_model_params() -> Mapping[str, str] | None:
    """Return the Benchmark-owned policy active for this Candidate task, if any."""

    return _candidate_model_params.get()


def apply_candidate_model_policy(params: Mapping[str, str]) -> dict[str, str]:
    """Combine one Model call with the active Benchmark-owned Candidate policy.

    A disabled Benchmark policy is authoritative. An enabled policy is a ceiling: a Candidate
    Model call may explicitly narrow it with ``web_search=false``. This lets the universal Fusion
    compiler keep synthesis retrieval-free without teaching the Engine about Fusion structure.
    """

    selected = dict(params)
    policy = current_candidate_model_params()
    if policy is None:
        return selected
    effective = {**selected, **policy}
    if policy.get("web_search") == "true" and selected.get("web_search") == "false":
        effective["web_search"] = "false"
        if "web_search_exclude" not in selected:
            effective.pop("web_search_exclude", None)
        if "web_search_policy" not in selected:
            effective.pop("web_search_policy", None)
    return effective


def record_candidate_finish_reason(finish_reason: str | None) -> None:
    """Retain one already-reported model response inside the active Candidate Invocation."""

    reasons = _candidate_finish_reasons.get()
    if reasons is not None:
        reasons.append(finish_reason)


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
        policy_token = _candidate_model_params.set(policy)
        reasons: list[str | None] = []
        response_token = _candidate_finish_reasons.set(reasons)
        try:
            result = await self._node.evaluate(
                request.intent,
                env={"input": request.context or ""},
            )
            # INVARIANT: the selected Candidate output is produced by the final model round trip.
            # Fusion synthesis depends on every member, and a tool loop's final answer follows its
            # tool-call turns, so the last reported reason is the output's reason.
            finish_reason = reasons[-1] if reasons else None
            return encode_candidate_invocation(result.text, finish_reason)
        finally:
            _candidate_finish_reasons.reset(response_token)
            _candidate_model_params.reset(policy_token)


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
    "apply_candidate_model_policy",
    "current_candidate_model_params",
    "install_candidate_invocation",
    "record_candidate_finish_reason",
]
