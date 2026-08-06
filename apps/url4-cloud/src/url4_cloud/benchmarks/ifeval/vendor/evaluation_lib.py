# ADAPTED VENDORED EXCERPT — source:
# https://github.com/google-research/google-research/blob/e6890f85757dd84e27ca6df2dd30651dafad28e0/instruction_following_eval/evaluation_lib.py
# Local change: the registry import is relative to this vendored package. CLI/file helpers that
# are irrelevant to protocol parity are omitted. Apache-2.0; see ./LICENSE.
# coding=utf-8
# Copyright 2026 The Google Research Authors.

"""Pinned official IFEval strict/loose protocol oracle."""

import dataclasses

from . import instructions_registry


@dataclasses.dataclass
class InputExample:
    key: int
    instruction_id_list: list[str]
    prompt: str
    kwargs: list[dict[str, object]]


@dataclasses.dataclass
class OutputExample:
    instruction_id_list: list[str]
    prompt: str
    response: str
    follow_all_instructions: bool
    follow_instruction_list: list[bool]


def test_instruction_following_strict(inp, response):
    """Official strict instruction check, copied from evaluation_lib.py."""

    is_following_list = []
    for index, instruction_id in enumerate(inp.instruction_id_list):
        instruction_cls = instructions_registry.INSTRUCTION_DICT[instruction_id]
        instruction = instruction_cls(instruction_id)
        instruction.build_description(**inp.kwargs[index])
        args = instruction.get_instruction_args()
        if args and "prompt" in args:
            instruction.build_description(prompt=inp.prompt)
        is_following_list.append(
            bool(response.strip() and instruction.check_following(response))
        )
    return OutputExample(
        instruction_id_list=inp.instruction_id_list,
        prompt=inp.prompt,
        response=response,
        follow_all_instructions=all(is_following_list),
        follow_instruction_list=is_following_list,
    )


def test_instruction_following_loose(inp, response):
    """Official eight-variant loose instruction check, copied from evaluation_lib.py."""

    lines = response.split("\n")
    response_remove_first = "\n".join(lines[1:]).strip()
    response_remove_last = "\n".join(lines[:-1]).strip()
    response_remove_both = "\n".join(lines[1:-1]).strip()
    revised_response = response.replace("*", "")
    all_responses = [
        response,
        revised_response,
        response_remove_first,
        response_remove_last,
        response_remove_both,
        response_remove_first.replace("*", ""),
        response_remove_last.replace("*", ""),
        response_remove_both.replace("*", ""),
    ]
    is_following_list = []
    for index, instruction_id in enumerate(inp.instruction_id_list):
        instruction_cls = instructions_registry.INSTRUCTION_DICT[instruction_id]
        instruction = instruction_cls(instruction_id)
        instruction.build_description(**inp.kwargs[index])
        args = instruction.get_instruction_args()
        if args and "prompt" in args:
            instruction.build_description(prompt=inp.prompt)
        is_following = any(
            candidate.strip() and instruction.check_following(candidate)
            for candidate in all_responses
        )
        is_following_list.append(bool(is_following))
    return OutputExample(
        instruction_id_list=inp.instruction_id_list,
        prompt=inp.prompt,
        response=response,
        follow_all_instructions=all(is_following_list),
        follow_instruction_list=is_following_list,
    )


__all__ = [
    "InputExample",
    "OutputExample",
    "test_instruction_following_loose",
    "test_instruction_following_strict",
]
