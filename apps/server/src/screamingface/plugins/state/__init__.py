"""state plugin — generic stateful storage core for plugins."""

from __future__ import annotations

from screamingface.plugins.state.base import BaseModel
from screamingface.plugins.state.store import BaseStore

__all__ = ["BaseModel", "BaseStore"]
