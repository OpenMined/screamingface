"""Prompt decoding, list parsing, and body building for url-executor."""

from __future__ import annotations

import base64
from typing import Any


def decode_prompt(params: dict[str, str], max_length: int) -> str:
    """Decode prompt from query params. ``pb`` (base64url) wins over ``p`` (plain text).

    Raises ValueError if prompt is missing or exceeds max_length.
    """
    raw: str | None = None

    if "pb" in params:
        encoded = params["pb"]
        # Add back padding if stripped
        padded = encoded + "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(padded).decode("utf-8")
    elif "p" in params:
        raw = params["p"]

    if raw is None:
        raise ValueError("Missing prompt: provide 'p' or 'pb' query parameter")

    if len(raw) > max_length:
        raise ValueError(f"Prompt exceeds maximum length of {max_length} characters")

    return raw


def parse_list(value: str | None) -> list[str] | None:
    """Parse a comma-separated string into a list. Returns None if empty."""
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


# Fields that should be parsed as comma-separated lists
_LIST_FIELDS = {"t", "at", "dt", "ad"}

# Fields that should be parsed as floats
_FLOAT_FIELDS = {"mb", "ts"}

# Fields that should be parsed as bools
_BOOL_FIELDS = {"dsp", "nsp"}


def build_dispatch_body(params: dict[str, str], prompt: str) -> dict[str, Any]:
    """Build the JSON body for the internal POST dispatch from query params.

    Uses the short alias names as keys (matching ClaudeRunRequest aliases).
    """
    body: dict[str, Any] = {"p": prompt}

    for key, value in params.items():
        if key in ("p", "pb", "stream"):
            continue
        if key in _LIST_FIELDS:
            parsed = parse_list(value)
            if parsed is not None:
                body[key] = parsed
        elif key in _FLOAT_FIELDS:
            body[key] = float(value)
        elif key in _BOOL_FIELDS:
            body[key] = value.lower() in ("1", "true", "yes")
        else:
            body[key] = value

    return body
