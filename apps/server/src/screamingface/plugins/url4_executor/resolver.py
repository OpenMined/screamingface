"""Backward-compatible re-exports from the interpreter module.

The canonical location is now ``interpreter.py``. This module exists
so existing imports keep working.
"""

from __future__ import annotations

from screamingface.plugins.url4_executor.interpreter import (  # noqa: F401
    resolve_intent as _resolve_intent,
)
from screamingface.plugins.url4_executor.url4 import _fetch_relative  # noqa: F401
