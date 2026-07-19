from __future__ import annotations

import pytest

import screamingface as sf
from screamingface import _execution
from screamingface._exact_choice import exact_choice_score, validate_exact_reference


@pytest.mark.parametrize(
    ("expected", "answer"),
    [
        ("D", "D"),
        ("D", "d"),
        ("C", "**C**"),
        ("B", "(B)"),
        ("B", "B."),
        ("B", '"B"'),
        ("I", "I"),
        ("B", "The answer is B."),
        ("D", "Final answer: D"),
        ("E", "The correct option is (E)."),
        ("H", "I'd choose option H here."),
        ("B", "I think the answer is B"),
        ("D", "The answer is a combination of factors, but D fits best."),
        ("A", "The answer is a."),
        ("A", "Answer: a"),
        ("A", "The answer is (a), because of the fever."),
        ("D", "d,"),
        ("B", "b!"),
        ("E", "The patient has a fever, so option E fits best."),
        ("D", "Answer B is tempting, but the final answer is D."),
        ("Paris", "paris."),
        ("3", "3"),
    ],
)
def test_exact_choice_accepts_proven_correct_answer_shapes(expected: object, answer: str) -> None:
    assert exact_choice_score(expected, answer) == 1.0


@pytest.mark.parametrize(
    ("expected", "answer"),
    [
        ("D", "I"),
        ("D", "The culture grew E. coli in this case."),
        ("D", "The correct answer is a beta-blocker."),
        ("D", "This is a hard question."),
        ("3", "2"),
        ("Paris", "London"),
    ],
)
def test_exact_choice_treats_wrong_or_unparseable_answers_as_valid_zero(
    expected: object, answer: str
) -> None:
    assert exact_choice_score(expected, answer) == 0.0


def test_exact_choice_empty_answer_is_wrong_and_non_string_answer_is_invalid() -> None:
    assert exact_choice_score("D", "") == 0.0
    with pytest.raises(TypeError, match="answer"):
        exact_choice_score("D", None)  # type: ignore[arg-type]


def test_exact_choice_accepts_a_decorated_conclusion_inside_prose() -> None:
    assert exact_choice_score("E", "After considering the evidence, (E) fits best.") == 1.0


@pytest.mark.parametrize(
    "reference",
    [None, "", "   ", True, 0, 3, 9, -1, 10, 1.5, {}, [], "!!!"],
)
def test_exact_choice_rejects_unusable_references(reference: object) -> None:
    with pytest.raises((TypeError, ValueError), match="reference"):
        validate_exact_reference(reference)


@pytest.mark.parametrize("reference", [str(index) for index in range(10)])
def test_exact_choice_accepts_numeric_string_indices_zero_through_nine(reference: str) -> None:
    assert validate_exact_reference(reference) == reference


def test_run_preflight_uses_the_shared_exact_reference_contract() -> None:
    valid = sf.Benchmark(
        "valid@1",
        cases=[sf.Case("q1", "Question", reference="3")],
        grader=sf.graders.ExactChoice(),
    )
    _execution._references(valid._materialize_cases(), valid)

    invalid = sf.Benchmark(
        "invalid@1",
        cases=[sf.Case("q1", "Question", reference=3)],
        grader=sf.graders.ExactChoice(),
    )
    with pytest.raises(sf.InvalidBenchmarkError, match="exact-choice reference"):
        _execution._references(invalid._materialize_cases(), invalid)
