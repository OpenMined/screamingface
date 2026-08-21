"""Host-environment capabilities shared across client features."""

from __future__ import annotations

import builtins
import sys


def running_in_notebook() -> bool:
    """Whether the active IPython host is an ipykernel-backed notebook."""
    get_ipython = getattr(builtins, "get_ipython", None)
    if not callable(get_ipython):
        return False
    try:
        shell = get_ipython()
    except Exception:  # pragma: no cover - defensive around a host-provided hook
        return False
    return shell is not None and shell.__class__.__module__.startswith("ipykernel")


def ipykernel_loaded() -> bool:
    """Whether ipykernel is loaded, the established progress-panel capability signal."""
    return "ipykernel" in sys.modules


__all__: list[str] = []
