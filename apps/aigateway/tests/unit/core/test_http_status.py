"""Strict provider HTTP-status validation (OME-428 third-review blocker E).

# STORY: as the gateway, I accept an upstream provider's numeric error status
# only when it is a real integer in the HTTP error range, so that a string,
# a Unicode digit, a float, or a bool can never crash rendering or smuggle an
# invalid status to the client.
# INVARIANT: exactly `type(value) is int and 400 <= value <= 599`. `isdigit()`
# is a trap: `"²".isdigit()` is True but `int("²")` raises ValueError, and the
# fullwidth `"４２９"` is silently accepted by `int()`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from aigateway.core.http_status import valid_http_error_status


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Valid integer statuses in range.
        (400, 400),
        (401, 401),
        (402, 402),
        (429, 429),
        (500, 500),
        (503, 503),
        (599, 599),
        # Out of the error range.
        (399, None),
        (200, None),
        (600, None),
        (0, None),
        (-1, None),
        # bool is an int subclass — must be rejected (int(True) == 1).
        (True, None),
        (False, None),
        # Strings are rejected wholesale (integer-only contract).
        ("429", None),
        ("0429", None),
        ("not-a-status", None),
        ("", None),
        # Unicode-digit hazards: isdigit() is True but these are not valid ints.
        ("²", None),  # int("²") would raise ValueError
        ("４２９", None),  # fullwidth digits: int() would silently accept -> 429
        # Floats (incl. non-finite) are rejected.
        (429.0, None),
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        # Decimal and other numeric-likes are rejected.
        (Decimal("429"), None),
        # None / arbitrary objects.
        (None, None),
        (object(), None),
        ([429], None),
    ],
)
def test_valid_http_error_status(value: object, expected: int | None) -> None:
    assert valid_http_error_status(value) == expected
