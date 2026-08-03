"""IFEval per-case grading — the vendored verifier behind a crash-safe boundary.

FEATURE: judge-free IFEval grading — every constraint checked by deterministic code.
STORY: as a researcher, my instruction-following score is exact and costs zero judge calls.
"""

from __future__ import annotations

import pytest

from url4_cloud.benchmarks.ifeval.grading import check_case


def test_no_comma_passes_a_comma_free_response() -> None:
    result = check_case(
        instruction_id_list=["punctuation:no_comma"],
        kwargs_list=[{}],
        prompt="Write about tea. Do not use commas.",
        response="Tea is a drink made from leaves and hot water.",
    )

    assert result["strict"] == [True]
    assert result["loose"] == [True]


def test_no_comma_fails_a_response_containing_a_comma() -> None:
    result = check_case(
        instruction_id_list=["punctuation:no_comma"],
        kwargs_list=[{}],
        prompt="Write about tea. Do not use commas.",
        response="Tea is warm, comforting and popular.",
    )

    assert result["strict"] == [False]
    assert result["loose"] == [False]


def test_word_count_boundary_is_inclusive_for_at_least() -> None:
    # INVARIANT: "at least N" passes at exactly N — the verifier's relation semantics are
    # the exam; an off-by-one here silently shifts every length-constrained score.
    kwargs = [{"relation": "at least", "num_words": 5}]

    exactly_five = check_case(
        instruction_id_list=["length_constraints:number_words"],
        kwargs_list=kwargs,
        prompt="Say something in five or more words.",
        response="one two three four five",
    )
    only_four = check_case(
        instruction_id_list=["length_constraints:number_words"],
        kwargs_list=kwargs,
        prompt="Say something in five or more words.",
        response="one two three four",
    )

    assert exactly_five["strict"] == [True]
    assert only_four["strict"] == [False]


def test_highlighted_sections_counts_asterisk_spans() -> None:
    result = check_case(
        instruction_id_list=["detectable_format:number_highlighted_sections"],
        kwargs_list=[{"num_highlights": 2}],
        prompt="Highlight at least two sections.",
        response="*first point* and also *second point* in the text",
    )

    assert result["strict"] == [True]


def test_loose_mode_recovers_a_quotation_wrapped_in_markdown() -> None:
    # WHY: the paper's loose protocol strips markdown emphasis and edge lines before
    # re-checking — a response that is compliant under any of the 8 variants counts loose.
    result = check_case(
        instruction_id_list=["startend:quotation"],
        kwargs_list=[{}],
        prompt="Wrap your whole answer in double quotes.",
        response='*"the whole answer"*',
    )

    assert result["strict"] == [False]
    assert result["loose"] == [True]


def test_repeat_prompt_requires_the_prompt_as_prefix() -> None:
    kwargs = [{"prompt_to_repeat": "Say hello to the team"}]

    repeated = check_case(
        instruction_id_list=["combination:repeat_prompt"],
        kwargs_list=kwargs,
        prompt="Say hello to the team",
        response="Say hello to the team\nHello team!",
    )
    unrepeated = check_case(
        instruction_id_list=["combination:repeat_prompt"],
        kwargs_list=kwargs,
        prompt="Say hello to the team",
        response="Hello team!",
    )

    assert repeated["strict"] == [True]
    assert unrepeated["strict"] == [False]


def test_multiple_instructions_report_positionally() -> None:
    result = check_case(
        instruction_id_list=[
            "punctuation:no_comma",
            "length_constraints:number_words",
        ],
        kwargs_list=[{}, {"relation": "at least", "num_words": 100}],
        prompt="No commas; at least 100 words.",
        response="Short and comma free answer.",
    )

    assert result["strict"] == [True, False]
    assert result["loose"] == [True, False]


def test_an_unknown_instruction_id_scores_false_instead_of_raising() -> None:
    # INVARIANT: a verifier crash is OUR bug, never the Candidate's judge-flake — the case
    # still scores (as failed) and `failures` stays empty. Deliberate divergence from
    # draco's unscored-never-zero rule, decided in OME-719.
    result = check_case(
        instruction_id_list=["bogus:not_an_instruction"],
        kwargs_list=[{}],
        prompt="anything",
        response="anything",
    )

    assert result["strict"] == [False]
    assert result["loose"] == [False]


def test_a_crashing_checker_scores_false_instead_of_raising() -> None:
    # combination:repeat_prompt without its required kwarg makes build_description raise.
    result = check_case(
        instruction_id_list=["combination:repeat_prompt"],
        kwargs_list=[{}],
        prompt="anything",
        response="anything",
    )

    assert result["strict"] == [False]
    assert result["loose"] == [False]


def test_mismatched_instruction_and_kwargs_lengths_raise() -> None:
    # WHY loud: positional parallelism is the dataset contract — a length skew means the
    # prepared assets are corrupt, not that the Candidate failed.
    with pytest.raises(ValueError):
        check_case(
            instruction_id_list=["punctuation:no_comma"],
            kwargs_list=[],
            prompt="anything",
            response="anything",
        )


def test_an_empty_response_fails_every_instruction() -> None:
    result = check_case(
        instruction_id_list=["punctuation:no_comma"],
        kwargs_list=[{}],
        prompt="anything",
        response="",
    )

    assert result["strict"] == [False]
    assert result["loose"] == [False]
