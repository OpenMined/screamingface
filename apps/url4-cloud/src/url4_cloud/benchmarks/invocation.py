"""Evaluate one complete Recipe into the shared Candidate Invocation envelope."""

from __future__ import annotations

from url4.core.errors import ResolutionError
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.candidate_execution import (
    capture_candidate_executions,
    terminal_candidate_execution,
)
from url4_cloud.benchmarks.contract import (
    PROVIDER_REFUSAL_PLACEHOLDER,
    CorrectiveExecution,
    encode_candidate_invocation,
)
from url4_cloud.model_outcomes import (
    ModelOutcome,
    capture_model_outcomes,
    model_outcome_from_error,
    terminal_model_outcome,
)


async def evaluate_candidate_recipe(
    node: Url4Node,
    expression: str,
    input_text: str,
    *,
    isolated: bool = False,
    input_binding: str = "input",
) -> str:
    """Evaluate a Recipe while preserving its exact terminal outcome."""

    with capture_candidate_executions(isolated=isolated) as executions:
        with capture_model_outcomes(isolated=isolated) as outcomes:
            try:
                result = await node.evaluate(expression, env={input_binding: input_text})
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
                # A content-filter turn often carries no refusal text. Preserve the
                # provider-refused path with an explicit gradeable marker rather than
                # making it indistinguishable from a successful empty answer.
                if not outcome.refusal:
                    outcome = ModelOutcome(outcome.finish_reason, PROVIDER_REFUSAL_PLACEHOLDER)
                return _encode("", outcome, terminal_candidate_execution(executions))

    return _encode(
        result.text,
        terminal_model_outcome(outcomes),
        terminal_candidate_execution(executions),
    )


def _encode(
    output: str,
    outcome: ModelOutcome,
    execution: CorrectiveExecution | None,
) -> str:
    try:
        return encode_candidate_invocation(
            output,
            outcome.finish_reason,
            outcome.refusal,
            execution,
        )
    except ValueError as exc:
        raise ResolutionError(
            str(exc),
            code="candidate_contract_error",
            permanent=True,
        ) from exc


__all__ = ["evaluate_candidate_recipe"]
