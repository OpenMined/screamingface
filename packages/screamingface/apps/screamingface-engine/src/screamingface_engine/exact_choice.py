"""Deterministic ExactChoice reference validation and answer scoring."""

from __future__ import annotations

import re

_WHOLE_LETTER_RE = re.compile(r"^[*_`\"'(\[]*([A-Ja-j])[)\]*_`\"'.:,;!?]*$")
_MARKER_RE = re.compile(
    r"(?:final\s+answer|correct\s+(?:answer|choice|option)|answer|option|choice)"
    r"\s*(?:is)?[\s:\-*_]*\(?([A-Ja-j])\)?(?![A-Za-z])",
    re.IGNORECASE,
)
_DECORATED_RE = re.compile(r"\(([A-J])\)|\b([A-J])\)")
_STANDALONE_RE = re.compile(r"\b([A-J])\b(?!\.\s*[a-z])")
_INDEX_RE = re.compile(r"\b([0-9])\b")
_PRONOUN_LETTERS = frozenset({"A", "I"})


def validate_exact_reference(reference: object) -> str:
    """Return one valid normalized-source reference without guessing its representation."""

    if not isinstance(reference, str) or not reference.strip():
        raise TypeError("exact-choice reference must be a non-empty string")
    normalized = reference.strip()
    if (
        _extract_letter(normalized) is None
        and _extract_index(normalized) is None
        and not _normalize(normalized)
    ):
        raise ValueError("exact-choice reference must contain usable answer text")
    return normalized


def exact_choice_score(reference: object, answer: str) -> float:
    """Return 1.0 for an exact normalized match and 0.0 for a valid wrong answer."""

    expected = validate_exact_reference(reference)
    if not isinstance(answer, str):
        raise TypeError("exact-choice answer must be a string")
    received = answer.strip()

    expected_letter = _extract_letter(expected)
    received_letter = _extract_letter(received)
    if expected_letter is not None and received_letter is not None:
        return float(expected_letter == received_letter)

    expected_index = _extract_index(expected)
    received_index = _extract_index(received)
    if expected_index is not None and received_index is not None:
        return float(expected_index == received_index)

    return float(bool(_normalize(expected)) and _normalize(expected) == _normalize(received))


def _extract_letter(text: str) -> str | None:
    """Extract the intended A-J choice, preferring the final explicit conclusion."""

    if not text:
        return None
    whole = _WHOLE_LETTER_RE.match(text.strip())
    if whole is not None:
        return whole.group(1).upper()
    candidates = _candidate_letters(text)
    return candidates[-1] if candidates else None


def _candidate_letters(text: str) -> list[str]:
    markers = _marker_letters(text)
    if markers:
        return [letter.upper() for letter in markers]

    decorated = [left or right for left, right in _DECORATED_RE.findall(text)]
    if decorated:
        return [letter.upper() for letter in decorated]

    standalone = _STANDALONE_RE.findall(text)
    non_pronoun = [letter for letter in standalone if letter not in _PRONOUN_LETTERS]
    return non_pronoun or standalone


def _marker_letters(text: str) -> list[str]:
    letters: list[str] = []
    for match in _MARKER_RE.finditer(text):
        letter = match.group(1)
        if (
            letter == "a"
            and "(" not in match.group(0)
            and re.match(r"\s+[A-Za-z]", text[match.end() :])
        ):
            continue
        letters.append(letter)
    return letters


def _extract_index(text: str) -> int | None:
    if not text:
        return None
    match = _INDEX_RE.search(text)
    return int(match.group(1)) if match is not None else None


def _normalize(text: str) -> str:
    return re.sub(r"\W+", "", text.lower())


__all__ = ["exact_choice_score", "validate_exact_reference"]
