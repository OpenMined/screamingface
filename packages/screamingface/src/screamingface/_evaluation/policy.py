"""Versioned SDK defaults for Candidate answer and synthesis policy."""

from __future__ import annotations

from collections.abc import Mapping

DEFAULT_ANSWER_PROMPT = (
    "Answer the request accurately and completely. "
    "Follow every instruction and formatting constraint in the request."
)
DEFAULT_SYNTHESIS_PROMPT = (
    "Produce the final answer to the original request. "
    "Synthesize the strongest supported answer from the panel responses, and follow every "
    "instruction and formatting constraint in the original request."
)
_DEFAULT_PARAMS: dict[str, str | int | float | bool] = {
    "max_tokens": 4096,
}


def resolved_params(
    overrides: Mapping[str, str | int | float | bool],
) -> tuple[tuple[str, str], ...]:
    merged = {**_DEFAULT_PARAMS, **overrides}
    return tuple((name, _scalar(value)) for name, value in merged.items())


def _scalar(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


__all__: list[str] = []
