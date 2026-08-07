"""Decode and classify one AI Gateway chat-completions choice."""

from __future__ import annotations

from dataclasses import dataclass

from url4_cloud.model_outcomes import ModelOutcome
from url4_cloud.runner.errors import RunnerRequestError


@dataclass(frozen=True, slots=True)
class Choice:
    """One chat-completions choice reduced to what the Runner consumes."""

    content: str | None
    tool_calls: list[dict] | None
    finish_reason: str | None
    refusal: str | None


def parse_choice(data: dict) -> Choice:
    """Pull the first choice out of a chat-completions response."""
    try:
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content")
        tool_calls = message.get("tool_calls")
        finish_reason = choice.get("finish_reason")
        refusal = message.get("refusal")
    except (KeyError, IndexError, TypeError) as exc:
        raise RunnerRequestError(
            "malformed aigateway response", code="aigateway_bad_response", permanent=True
        ) from exc
    return Choice(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        refusal=refusal if isinstance(refusal, str) and refusal.strip() else None,
    )


def raise_if_unusable(choice: Choice) -> None:
    """Reject a refusal or a choice carrying neither answer nor tool call."""
    # INVARIANT: refusal precedes emptiness because content-filter turns normally carry null text.
    if choice.finish_reason == "content_filter" or choice.refusal is not None:
        raise RunnerRequestError(
            "provider refused the request",
            code="provider_refusal",
            permanent=True,
            outcome=ModelOutcome(choice.finish_reason, choice.refusal),
        )
    if not choice.tool_calls and choice.content is None:
        raise RunnerRequestError(
            "malformed aigateway response", code="aigateway_bad_response", permanent=True
        )
