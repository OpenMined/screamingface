"""Candidate Invocation adapter installed into the shared Runner URL4 world."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.contract import (
    CANDIDATE_ROUTE,
    encode_candidate_invocation,
)
from url4_cloud.model_outcomes import (
    ModelOutcome,
    capture_model_outcomes,
    model_outcome_from_error,
)
from url4_cloud.retrieval_policy import (
    RetrievalPolicy,
    RetrievalPolicyError,
    normalize_excluded_domains,
    retrieval_scope,
)

_POLICY_PARAMS = frozenset({"web_search", "web_search_exclude"})


class _CandidateInvocation:
    """Evaluate linked Candidate URL4 in the same world under a narrower ambient policy."""

    __slots__ = ("_node",)

    def __init__(self, node: Url4Node) -> None:
        self._node = node

    async def __call__(self, request: Request) -> str:
        if not request.intent.strip():
            raise ResolutionError(
                "Candidate Invocation expression must be non-empty",
                code="candidate_contract_error",
                permanent=True,
            )
        policy = _candidate_policy(request.params)
        outcomes: list[ModelOutcome]
        try:
            with retrieval_scope(policy), capture_model_outcomes() as outcomes:
                try:
                    result = await self._node.evaluate(
                        request.intent,
                        env={"input": request.context or ""},
                    )
                except ResolutionError as exc:
                    if exc.code != "provider_refusal":
                        raise
                    outcome = model_outcome_from_error(exc)
                    if outcome is None:
                        raise ResolutionError(
                            "provider refusal carried no terminal outcome",
                            code="candidate_contract_error",
                            permanent=True,
                        ) from exc
                    return _encode_candidate_invocation("", outcome)
        except RetrievalPolicyError as exc:
            raise ResolutionError(
                str(exc),
                code="candidate_policy_escalation",
                permanent=True,
            ) from exc

        return _encode_candidate_invocation(result.text, _terminal_outcome(outcomes))


def _terminal_outcome(outcomes: Sequence[ModelOutcome]) -> ModelOutcome:
    """Return the outcome that describes the returned answer, or state that none is known.

    A Candidate composes ordinary URL4, so one scope may record several terminal outcomes while
    the recorder cannot say which branch produced the text that came back. Taking the most recent
    one attributes a sibling's fields to an unrelated answer, and can pair a non-empty output with
    a refusal — a shape the contract does not admit. Unanimity is not ambiguity, so agreeing
    branches still describe the answer; disagreeing ones report null, which the contract allows.
    A benchmark that needs per-call fidelity must invoke one Candidate per model call.
    """

    distinct = set(outcomes)
    return distinct.pop() if len(distinct) == 1 else ModelOutcome(None, None)


def install_candidate_invocation(node: Url4Node) -> None:
    """Install the one Engine-owned Candidate adapter on ``node``."""

    node.endpoint(CANDIDATE_ROUTE)(_CandidateInvocation(node))


def _encode_candidate_invocation(output: str, outcome: ModelOutcome) -> str:
    try:
        return encode_candidate_invocation(
            output,
            outcome.finish_reason,
            outcome.refusal,
        )
    except ValueError as exc:
        raise ResolutionError(
            str(exc),
            code="candidate_contract_error",
            permanent=True,
        ) from exc


def _candidate_policy(params: Mapping[str, str]) -> RetrievalPolicy:
    unknown = sorted(set(params) - _POLICY_PARAMS)
    if unknown:
        raise ResolutionError(
            f"unsupported Candidate policy parameter(s) {unknown}",
            code="candidate_policy_invalid",
            permanent=True,
        )
    raw_search = params.get("web_search")
    if raw_search not in {"true", "false"}:
        raise ResolutionError(
            "Candidate policy requires web_search=true or web_search=false",
            code="candidate_policy_invalid",
            permanent=True,
        )
    excluded = _excluded_domains(params.get("web_search_exclude"))
    if raw_search == "false" and excluded:
        raise ResolutionError(
            "web_search_exclude requires web_search=true",
            code="candidate_policy_invalid",
            permanent=True,
        )
    return RetrievalPolicy(web_search=raw_search == "true", excluded_domains=excluded)


def _excluded_domains(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, str):
        raise ResolutionError(
            "web_search_exclude must be a colon-separated list of bare domains",
            code="candidate_policy_invalid",
            permanent=True,
        )
    try:
        return normalize_excluded_domains(value.split(":"))
    except ValueError as exc:
        raise ResolutionError(
            "web_search_exclude must be a colon-separated list of bare domains",
            code="candidate_policy_invalid",
            permanent=True,
        ) from exc


__all__ = ["install_candidate_invocation"]
