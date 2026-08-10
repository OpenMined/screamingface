"""Canonical money spelling for provider-authored cost evidence (OME-303 §3.5).

FEATURE: per-provider-call usage accounting. AIGateway reports what a provider said
a call cost; Engine converts, attributes and sums it.

INVARIANT: one value has exactly one wire spelling. Engine sums these strings across
runs and deployments, so ``"1"`` and ``"1.000"`` arriving for the same cost would be
two different values to anything that compares or de-duplicates them.

INVARIANT: never ``Decimal(float)``. A provider hands us a JSON number that Python
parses to a binary float; ``Decimal(0.1)`` preserves the binary artefact
(0.1000000000000000055511151231257827021181583404541015625) while
``Decimal(str(0.1))`` is exactly ``0.1``. The artefact is what would reach Engine.

INVARIANT: unknown is ``None``, never ``"0"``. A missing cost field means the provider
did not tell us; rendering it as zero would invent a provider-authored claim that the
call was free.

AIDEV-NOTE: this deliberately mirrors ``openrouter_provider.routing_policy.normalize_price``
rather than importing it — core may not import a plugin (repo architecture rule). The two
must stay spelled the same way; ``format(Decimal(v), "f")`` plus a decimal-point-conditional
trailing-zero strip is the whole contract.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

__all__ = ["canonical_amount", "sum_amounts"]


def _to_decimal(value: object) -> Decimal | None:
    """A finite ``Decimal`` for a safely-numeric value, else ``None``.

    ``bool`` is refused explicitly: it is an ``int`` subclass in Python, so a stray
    ``True`` would otherwise render as the cost ``"1"``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, (int, float, str)):
        try:
            # INVARIANT: str() first — see the module docstring on Decimal(float).
            candidate = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    else:
        return None
    if not candidate.is_finite():
        # NaN and +/-Inf are not amounts. A provider that sends one has told us nothing.
        return None
    return candidate


def _render(candidate: Decimal) -> str:
    """Exact fixed-point text with one spelling per value.

    WHY ``format(…, "f")`` and not ``Decimal.normalize()``: ``normalize()`` is bounded
    by the decimal context's precision so it would round a long value, and it renders
    ``100`` as ``"1E+2"`` — an exponent spelling this contract does not use.

    WHY the strip is conditional on a decimal point: an unconditional ``rstrip("0")``
    turns ``"10"`` into ``"1"``, a tenfold change to a real cost.
    """
    text = format(candidate, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    # "-0" and "0.000" both mean zero; give zero one spelling too.
    return "0" if text in ("-0", "") else text


def _bounded_render(candidate: Decimal) -> str | None:
    """Canonical nonnegative v1 amount within the public precision bound."""
    if candidate < 0:
        return None
    if candidate.is_zero():
        return "0"
    parts = candidate.as_tuple()
    digits = list(parts.digits)
    exponent = int(parts.exponent)
    while exponent < 0 and digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    integer_digits = len(digits) + exponent if exponent >= 0 else max(len(digits) + exponent, 1)
    fractional_digits = 0 if exponent >= 0 else -exponent
    if integer_digits > 18 or fractional_digits > 18:
        return None
    return _render(candidate)


def canonical_amount(value: object) -> str | None:
    """Canonical fixed-point text for ``value``, or ``None`` when it is not an amount.

    ``None`` means "unknown or unsafe evidence". An explicit provider-reported zero
    survives as ``"0"`` — the two are different claims and must stay distinguishable.
    """
    candidate = _to_decimal(value)
    return None if candidate is None else _bounded_render(candidate)


def sum_amounts(amounts: Iterable[str]) -> str | None:
    """Decimal sum of canonical amount strings, or ``None``.

    INVARIANT: an unparseable member poisons the whole sum. Skipping it would emit a
    total that silently under-reports spend while still presenting itself as a total —
    the caller cannot tell a complete sum from a lossy one, so refuse instead. The
    renderer pairs this with a non-complete ``direct_cost_status``.
    """
    canonical: list[str] = []
    for amount in amounts:
        rendered = canonical_amount(amount)
        if rendered is None:
            return None
        canonical.append(rendered)
    if not canonical:
        return None
    scale = max(len(value.partition(".")[2]) if "." in value else 0 for value in canonical)
    factor = 10**scale
    total = 0
    for value in canonical:
        integer, separator, fraction = value.partition(".")
        total += int(integer) * factor
        if separator:
            total += int(fraction.ljust(scale, "0"))
    whole, remainder = divmod(total, factor)
    if len(str(whole)) > 18:
        return None
    if scale == 0 or remainder == 0:
        return str(whole)
    fractional = str(remainder).zfill(scale).rstrip("0")
    return f"{whole}.{fractional}"
