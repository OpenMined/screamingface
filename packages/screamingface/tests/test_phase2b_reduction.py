from __future__ import annotations

import pytest

from screamingface._reduction import select_majority


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        (("A", "B", "A"), "A"),
        (("A", "a", "a"), "a"),
        (("A", "A\n", "B"), "A"),
        (("second", "first"), "second"),
    ],
)
def test_select_majority_uses_exact_strings_and_stable_input_order(
    answers: tuple[str, ...], expected: str
) -> None:
    assert select_majority(answers) == expected


@pytest.mark.parametrize(
    ("answers", "error", "message"),
    [
        ((), ValueError, "at least two"),
        (("only",), ValueError, "at least two"),
        ("AB", ValueError, "at least two"),
        (("A", "  "), ValueError, "blank"),
        (("A", 1), TypeError, "strings"),
    ],
)
def test_select_majority_rejects_invalid_answers(
    answers: object, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        select_majority(answers)  # type: ignore[arg-type]
