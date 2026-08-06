"""Per-case IFEval grading — the vendored verifier behind a crash-safe boundary.

Reimplements the ~40 protocol lines of the fork's ``evaluation.py`` (its typer/rich CLI
wrapper is not vendored) over the vendored ``instructions_registry``.

INVARIANT: the strict and loose protocols mirror the fork's ``test_instruction_following``
EXACTLY — the loose variant list, the empty-variant skip, and the ``prompt`` rebuild are
the exam. A different reading is a different benchmark.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CaseVerification:
    strict: tuple[bool, ...]
    loose: tuple[bool, ...]
    descriptions: tuple[str, ...]


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

    verified = verify_case(
        instruction_id_list=instruction_id_list,
        kwargs_list=kwargs_list,
        prompt=prompt,
        response=response,
    )
    return {"strict": list(verified.strict), "loose": list(verified.loose)}


def verify_case(
    *,
    instruction_id_list: Sequence[str],
    kwargs_list: Sequence[Mapping[str, Any]],
    prompt: str,
    response: str,
) -> CaseVerification:
    """Return verdicts and the exact descriptions instantiated for the strict pass."""

    if len(instruction_id_list) != len(kwargs_list):
        raise ValueError(
            "instruction_id_list and kwargs must be positionally parallel — "
            f"got {len(instruction_id_list)} instructions and {len(kwargs_list)} kwargs"
        )
    loose_responses = _loose_variants(response)
    # The official evaluator completes the strict pass over every instruction before it
    # starts the loose pass. That ordering matters for the benchmark's one randomized upstream
    # checker, so do not interleave strict/loose checks per instruction.
    pairs = tuple(zip(instruction_id_list, kwargs_list, strict=True))
    strict_results = [
        _follows(instruction_id, kwargs, prompt, [response]) for instruction_id, kwargs in pairs
    ]
    loose = [
        _follows(instruction_id, kwargs, prompt, loose_responses)[0]
        for instruction_id, kwargs in pairs
    ]
    return CaseVerification(
        strict=tuple(passed for passed, _description in strict_results),
        loose=tuple(loose),
        descriptions=tuple(description for _passed, description in strict_results),
    )


def failed_descriptions(verification: CaseVerification) -> list[str]:
    """Return the exact strict-pass descriptions for failed instructions."""

    return [
        description
        for description, passed in zip(
            verification.descriptions,
            verification.strict,
            strict=True,
        )
        if not passed
    ]


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
) -> tuple[bool, str]:
    from url4_cloud.benchmarks.ifeval.vendor import instructions_registry

    instruction_cls = instructions_registry.INSTRUCTION_DICT[instruction_id]
    instruction = instruction_cls(instruction_id)
    description = instruction.build_description(**kwargs)
    args = instruction.get_instruction_args()
    if args and "prompt" in args:
        description = instruction.build_description(prompt=prompt)
    follows = any(
        response.strip() and instruction.check_following(response) for response in responses
    )
    return follows, str(description)


__all__ = [
    "CaseVerification",
    "check_case",
    "configure_nltk",
    "failed_descriptions",
    "verify_case",
]
