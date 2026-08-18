"""Shared scalar validation for DRACO wire and asset records."""

from __future__ import annotations


def optional_integer(value: object) -> int | None:
    """Return an integer carried as JSON integer/text, excluding booleans and other coercions."""

    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def require_positive_integer(value: object, label: str) -> int:
    """Decode one positive integer or raise a field-specific validation error."""

    selected = optional_integer(value)
    if selected is None or selected < 1:
        raise ValueError(f"{label} must be a positive integer")
    return selected


def require_text(value: object, label: str) -> str:
    """Decode one non-empty text field without normalizing its contents."""

    if not has_text(value):
        raise ValueError(f"{label} must be non-empty text")
    assert isinstance(value, str)
    return value


def has_text(value: object) -> bool:
    """Return whether a wire value is non-empty text."""

    return isinstance(value, str) and bool(value.strip())


__all__ = ["has_text", "optional_integer", "require_positive_integer", "require_text"]
