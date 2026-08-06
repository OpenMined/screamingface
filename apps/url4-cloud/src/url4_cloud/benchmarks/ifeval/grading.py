"""Per-case IFEval grading — the vendored verifier behind a crash-safe boundary.

Reimplements the ~40 protocol lines of the fork's ``evaluation.py`` (its typer/rich CLI
wrapper is not vendored) over the vendored ``instructions_registry``.

INVARIANT: the strict and loose protocols mirror the fork's ``test_instruction_following``
EXACTLY — the loose variant list, the empty-variant skip, and the ``prompt`` rebuild are
the exam. A different reading is a different benchmark.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def configure_nltk(data_dir: Path) -> None:
    """Point nltk at the prepared offline corpus, once.

    INVARIANT: the verifier's own ``ensure_nltk_resource`` downloader is NEVER called — a
    Runner Job has a read-only rootfs and no network egress, so tokenizer data must come
    from the benchmark's prepared assets.
    """

    import nltk

    selected = str(data_dir)
    if data_dir.is_dir() and selected not in nltk.data.path:
        nltk.data.path.insert(0, selected)


def check_case(
    *,
    instruction_id_list: Sequence[str],
    kwargs_list: Sequence[Mapping[str, Any]],
    prompt: str,
    response: str,
) -> dict[str, list[bool]]:
    """Check one response against its case's constraints, strict and loose."""

    if len(instruction_id_list) != len(kwargs_list):
        raise ValueError(
            "instruction_id_list and kwargs must be positionally parallel — "
            f"got {len(instruction_id_list)} instructions and {len(kwargs_list)} kwargs"
        )
    loose_responses = _loose_variants(response)
    strict: list[bool] = []
    loose: list[bool] = []
    for instruction_id, kwargs in zip(instruction_id_list, kwargs_list, strict=True):
        strict.append(_follows(instruction_id, kwargs, prompt, [response]))
        loose.append(_follows(instruction_id, kwargs, prompt, loose_responses))
    return {"strict": strict, "loose": loose}


def describe_failures(
    *,
    instruction_id_list: Sequence[str],
    kwargs_list: Sequence[Mapping[str, Any]],
    prompt: str,
    strict: Sequence[bool],
) -> list[str]:
    """The checker's own wording for every failed instruction — the retry's feedback.

    WHY the verifier's own ``build_description`` text: the feedback a corrective
    attempt sees must describe the constraint exactly as the checker enforces it —
    a paraphrase could drift from what the exam actually grades.
    """

    if not (len(instruction_id_list) == len(kwargs_list) == len(strict)):
        raise ValueError("instruction ids, kwargs and verdicts must be positionally parallel")
    return [
        _describe(instruction_id, kwargs, prompt)
        for instruction_id, kwargs, passed in zip(
            instruction_id_list, kwargs_list, strict, strict=True
        )
        if not passed
    ]


def describe_instructions(
    *,
    instruction_id_list: Sequence[str],
    kwargs_list: Sequence[Mapping[str, Any]],
    prompt: str,
) -> list[str]:
    """Return the official human-readable description of every checked constraint."""

    if len(instruction_id_list) != len(kwargs_list):
        raise ValueError("instruction ids and kwargs must be positionally parallel")
    return [
        _describe(instruction_id, kwargs, prompt)
        for instruction_id, kwargs in zip(instruction_id_list, kwargs_list, strict=True)
    ]


def _describe(instruction_id: str, kwargs: Mapping[str, Any], prompt: str) -> str:
    from url4_cloud.benchmarks.ifeval.vendor import instructions_registry

    try:
        instruction_cls = instructions_registry.INSTRUCTION_DICT[instruction_id]
        instruction = instruction_cls(instruction_id)
        description = instruction.build_description(**kwargs)
        args = instruction.get_instruction_args()
        if args and "prompt" in args:
            description = instruction.build_description(prompt=prompt)
        return str(description)
    except Exception:  # noqa: BLE001
        # Same crash-policy boundary as _follows: a describer bug must never take the
        # whole check down. Keep the fallback generic because instruction identifiers
        # are private grading material and must not enter Candidate context.
        return "One instruction requirement was not satisfied."


def _loose_variants(response: str) -> list[str]:
    # IFEval's loose protocol (Zhou et al., arXiv:2311.07911): the response plus 7
    # markdown/edge-line-stripped variants;
    # compliant under ANY variant counts. Mirrors evaluation.py verbatim.
    variants = [
        response,
        response.replace("*", ""),
        "\n".join(response.split("\n")[1:]).strip(),
        "\n".join(response.split("\n")[:-1]).strip(),
        "\n".join(response.split("\n")[1:-1]).strip(),
    ]
    variants += [variant.replace("*", "") for variant in variants[2:]]
    return variants


def _follows(
    instruction_id: str,
    kwargs: Mapping[str, Any],
    prompt: str,
    responses: Sequence[str],
) -> bool:
    from url4_cloud.benchmarks.ifeval.vendor import instructions_registry

    instruction_cls = instructions_registry.INSTRUCTION_DICT[instruction_id]
    instruction = instruction_cls(instruction_id)
    instruction.build_description(**kwargs)
    args = instruction.get_instruction_args()
    if args and "prompt" in args:
        instruction.build_description(prompt=prompt)
    return any(response.strip() and instruction.check_following(response) for response in responses)


__all__ = ["check_case", "configure_nltk", "describe_failures", "describe_instructions"]
