"""Shared safe errors and JSON decoding for engine connection control."""

from __future__ import annotations

import json
from typing import Any


class ConnectionControlError(Exception):
    """A sanitized connection-control failure safe for the public engine boundary."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        provider: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.status = status
        self.code = code
        self.provider = provider
        self.retryable = retryable
        super().__init__(message)


def parse_unique_json_object(body: str) -> dict[str, object]:
    """Decode one JSON object while rejecting ambiguous duplicate fields."""

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(body, object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise ValueError("response is not JSON") from exc
    if not isinstance(value, dict):
        raise TypeError("expected a JSON object")
    return value


__all__ = ["ConnectionControlError", "parse_unique_json_object"]
