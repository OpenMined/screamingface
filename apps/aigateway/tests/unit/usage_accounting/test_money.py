"""OME-303 §3.5 — canonical money spelling for provider-authored cost evidence.

INVARIANT under test: one value has exactly one wire spelling, it is never an
exponent, and it is never reached through ``Decimal(float)``. Engine sums these
strings across runs, so a spelling drift is a silent accounting drift.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from aigateway.core.usage_accounting import canonical_amount, sum_amounts


class TestCanonicalAmount:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0.0012, "0.0012"),
            ("0.0012", "0.0012"),
            (0, "0"),
            (0.0, "0"),
            ("0", "0"),
            (1, "1"),
            (Decimal("0.0012"), "0.0012"),
            ("0.0038799200000000002", "0.0038799200000000002"),
            (
                "0.123456789012345678901234567890123",
                "0.123456789012345678901234567890123",
            ),
        ],
    )
    def test_renders_canonical_fixed_point(self, value: object, expected: str) -> None:
        assert canonical_amount(value) == expected

    @pytest.mark.parametrize("value", [1e-7, 1e-9, 0.000000123])
    def test_never_emits_exponent_notation(self, value: float) -> None:
        rendered = canonical_amount(value)
        assert rendered is not None
        assert "e" not in rendered.lower()
        assert Decimal(rendered) == Decimal(str(value))

    def test_goes_through_str_not_binary_float(self) -> None:
        # WHY: ``Decimal(0.1)`` is 0.1000000000000000055511151231257827021181583404541015625.
        # ``Decimal(str(0.1))`` is exactly "0.1". Engine must never be handed the artefact.
        assert canonical_amount(0.1) == "0.1"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("1.000", "1"), ("10", "10"), ("0.100", "0.1"), ("1.0", "1")],
    )
    def test_one_value_has_one_spelling(self, value: str, expected: str) -> None:
        # Mirrors the OpenRouter ``normalize_price`` discipline: the trailing-zero
        # strip is CONDITIONAL on a decimal point, so "10" never becomes "1".
        assert canonical_amount(value) == expected

    @pytest.mark.parametrize(
        "value", [None, "", "abc", float("nan"), float("inf"), True, False, [], {}, object()]
    )
    def test_unsafe_or_absent_evidence_is_none_never_zero(self, value: object) -> None:
        # INVARIANT (§3.5): unknown is null. Coercing it to "0" would invent a
        # provider-authored claim that the request was free.
        assert canonical_amount(value) is None

    @pytest.mark.parametrize(
        "value",
        ["-1", "1000000000000000000", "0.1234567890123456789012345678901234"],
    )
    def test_out_of_contract_amounts_are_invalid_not_mapper_exceptions(self, value: str) -> None:
        assert canonical_amount(value) is None

    @pytest.mark.parametrize("value", ["1e100000", "1e-100000"])
    def test_compact_exponents_are_rejected_before_fixed_point_expansion(self, value: str) -> None:
        assert canonical_amount(value) is None


class TestSumAmounts:
    def test_sums_with_decimal_not_float(self) -> None:
        # 0.1 + 0.2 is 0.30000000000000004 in binary float.
        assert sum_amounts(["0.1", "0.2"]) == "0.3"

    def test_empty_sum_is_none(self) -> None:
        assert sum_amounts([]) is None

    def test_preserves_small_magnitudes_without_exponent(self) -> None:
        total = sum_amounts(["0.0000001", "0.0000002"])
        assert total == "0.0000003"

    def test_unparseable_member_poisons_the_sum(self) -> None:
        # INVARIANT: a summary that silently drops an unknown member would under-report
        # spend while still claiming to be a total. Refuse instead.
        assert sum_amounts(["0.1", "not-a-number"]) is None

    def test_sum_that_exceeds_wire_precision_is_refused(self) -> None:
        assert sum_amounts(["999999999999999999", "999999999999999999"]) is None

    def test_sum_is_exact_beyond_the_default_decimal_context(self) -> None:
        assert (
            sum_amounts(
                [
                    "999999999999999999.000000000000000001",
                    "0.000000000000000001",
                ]
            )
            == "999999999999999999.000000000000000002"
        )

    def test_sum_preserves_the_full_fractional_bound(self) -> None:
        assert (
            sum_amounts(
                ["0.123456789012345678901234567890122", "0.000000000000000000000000000000001"]
            )
            == "0.123456789012345678901234567890123"
        )
