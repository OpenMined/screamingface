"""``CostBreakdown`` — a total with an optional partial per-class breakdown.

FEATURE: per-run cost reporting (`OME-849`). A provider may author the cost of a call as a single
amount with no per-class split — OpenRouter reports exactly that. The breakdown is therefore
evidence a producer MAY have, not evidence it must fabricate.

STORY: as a researcher reading a run Report, I see the real cost of my run even when the provider
told the gateway only a total, and I never see a total that claims less than its own parts.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from url4.streaming.protocol.taxonomy import CostBreakdown


def test_a_total_with_no_breakdown_is_accepted() -> None:
    """The OpenRouter shape: one provider-authored amount, no per-class split.

    INVARIANT: this is the case the feature exists for. Rejecting it would force a producer to
    invent a split it does not have.
    """
    cost = CostBreakdown(total_usd=Decimal("0.001"))

    assert cost.total_usd == Decimal("0.001")
    assert cost.input_usd == Decimal("0")
    assert cost.output_usd == Decimal("0")


def test_a_complete_breakdown_summing_to_the_total_is_accepted() -> None:
    """Pre-existing behaviour, preserved: a fully-specified breakdown still validates."""
    cost = CostBreakdown(
        input_usd=Decimal("0.10"),
        output_usd=Decimal("0.20"),
        cache_read_usd=Decimal("0.01"),
        cache_creation_usd=Decimal("0.02"),
        reasoning_usd=Decimal("0.03"),
        total_usd=Decimal("0.36"),
    )

    assert cost.total_usd == Decimal("0.36")


def test_a_partial_breakdown_below_the_total_is_accepted() -> None:
    """Some classes known, others not — the total stays authoritative."""
    cost = CostBreakdown(input_usd=Decimal("0.10"), total_usd=Decimal("0.36"))

    assert cost.input_usd == Decimal("0.10")
    assert cost.total_usd == Decimal("0.36")


def test_a_breakdown_exceeding_the_total_is_rejected() -> None:
    """INVARIANT: components may be incomplete, never larger than the whole.

    A breakdown claiming more than the total is incoherent whichever number you trust, so it stays
    an error. This is the half of the old equality rule that must survive.
    """
    with pytest.raises(ValidationError):
        CostBreakdown(input_usd=Decimal("0.40"), total_usd=Decimal("0.36"))


def test_zero_with_no_breakdown_is_accepted() -> None:
    """The shape url4-cloud publishes for an unpriced run today — must not regress."""
    assert CostBreakdown(total_usd=Decimal("0")).total_usd == Decimal("0")


def test_a_partial_breakdown_keeps_exact_decimal_precision() -> None:
    """INVARIANT: money never round-trips through binary float.

    The relaxed comparison must not coerce either side — a sub-cent total has to survive intact,
    because these amounts are summed downstream across a whole run.
    """
    total = Decimal("0.000000000000000001")
    cost = CostBreakdown(input_usd=Decimal("0.0000000000000000005"), total_usd=total)

    assert cost.total_usd == total
    assert str(cost.total_usd) == "1E-18"
