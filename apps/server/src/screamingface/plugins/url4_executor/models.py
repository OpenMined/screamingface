"""Models for the url-executor plugin."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UrlExecParams:
    """Parsed parameters from the URL query string."""

    backend: str
    action: str
    prompt: str
    stream: bool = False
    extra: dict | None = None
