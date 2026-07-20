"""Retry-After parsing rejects non-finite values (OME-428 second-review FINDING C).

``_seconds_from_headers`` currently accepts ``float("Infinity")`` / ``float("1e309")``
→ ``inf`` and ``float("NaN")`` → ``nan``. Downstream:

- ``_retry_after_headers`` calls ``math.ceil(inf)`` → ``OverflowError`` → HTTP 500.
- ``nan`` slips through ``max(0.0, nan)`` → ``0.0`` → an *invented* ``Retry-After: 0``
  that the provider never sent.

Only a non-negative ASCII integer delta-seconds value is supported; anything else
must return ``None`` so the caller falls back to bounded exponential backoff and no
``Retry-After`` header is fabricated.

INVARIANT: preserve a validated Retry-After; never fabricate one from a
malformed/non-finite value.
"""

from __future__ import annotations

import pytest

from aigateway.core.retry import parse_retry_after_seconds
from aigateway.routes.chat_dispatch import _retry_after_headers


class _HeaderExc(Exception):
    """A FastAPI-style exception exposing ``.headers`` (how the aigateway plugins
    surface upstream Retry-After hints)."""

    def __init__(self, retry_after: str) -> None:
        super().__init__("upstream")
        self.headers = {"Retry-After": retry_after}


@pytest.mark.parametrize("raw", ["Infinity", "inf", "1e309", "-1e309", "NaN", "nan"])
def test_non_finite_retry_after_is_rejected(raw: str) -> None:
    # Non-finite (or overflowing) values are not a valid delta-seconds hint.
    assert parse_retry_after_seconds(_HeaderExc(raw)) is None


@pytest.mark.parametrize("raw", ["not-a-number", "", "soon"])
def test_unparseable_retry_after_is_rejected(raw: str) -> None:
    assert parse_retry_after_seconds(_HeaderExc(raw)) is None


@pytest.mark.parametrize(("raw", "expected"), [("7", 7.0), ("0", 0.0)])
def test_integer_retry_after_is_preserved(raw: str, expected: float) -> None:
    assert parse_retry_after_seconds(_HeaderExc(raw)) == expected


@pytest.mark.parametrize("raw", ["-5", "+7", "3.2", "1e3", "４２９"])
def test_non_integer_delta_seconds_are_rejected(raw: str) -> None:
    assert parse_retry_after_seconds(_HeaderExc(raw)) is None


def test_retry_after_header_not_fabricated_for_non_finite() -> None:
    # Current code: math.ceil(inf) → OverflowError → HTTP 500.
    assert _retry_after_headers(_HeaderExc("Infinity")) == {}


def test_retry_after_header_not_fabricated_for_nan() -> None:
    # Current code: nan → max(0.0, nan) → 0.0 → invented "Retry-After: 0".
    assert _retry_after_headers(_HeaderExc("NaN")) == {}


def test_retry_after_header_preserves_integer() -> None:
    assert _retry_after_headers(_HeaderExc("3.2")) == {}
    assert _retry_after_headers(_HeaderExc("7")) == {"Retry-After": "7"}
