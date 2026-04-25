"""Small cross-plugin utilities that live above any single plugin.

Currently holds :func:`get_plugins_registry`, which lets plugin code
reach the active-plugin registry through a single named invariant
instead of defensively walking ``getattr(app, "state", None)`` every
time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from screamingface.core.registry import PluginRegistry


def get_plugins_registry(app: Any) -> PluginRegistry:
    """Return ``app.state.plugins``, raising if the invariant is broken.

    The SF bootstrap (:func:`screamingface.core.app.create_app`) always
    sets ``app.state.plugins`` before the first request lands. Plugin
    code that needs to walk the active-plugin list can rely on that
    invariant — the defensive ``getattr(getattr(app, "state", None),
    "plugins", None)`` dance was only there because we didn't have a
    single assertion point.

    Raises:
        RuntimeError: ``app.state.plugins`` is missing. This indicates
            a broken bootstrap path (test harness that skipped
            ``create_app``, or plugin ``setup()`` running before the
            registry was attached).
    """
    state = getattr(app, "state", None)
    registry = getattr(state, "plugins", None) if state is not None else None
    if registry is None:
        raise RuntimeError(
            "app.state.plugins is not set — the SF bootstrap did not run. "
            "This usually means a test harness is using a bare FastAPI app "
            "instead of screamingface.core.app.create_app()."
        )
    return registry
