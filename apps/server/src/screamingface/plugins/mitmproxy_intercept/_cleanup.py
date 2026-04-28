"""Stale-state cleanup for the mitmproxy intercept plugin.

If mitmdump crashes without a clean shutdown, two artifacts persist:

- The macOS Network Extension keeps redirecting traffic into a
  process that no longer exists.
- ``state.json`` records the dead PID so subsequent activations think
  another instance is already running.

:func:`cleanup_stale` clears both. :func:`clear_intercept` connects
to the still-running redirector app and resets its intercept spec to
empty, which is the macOS-friendly way to drain redirected traffic.

Pulled out of ``plugin.py`` during SF-134.
"""

from __future__ import annotations

import logging
import os
import signal

from screamingface.plugins.mitmproxy_intercept.state import clear_state, load_state

logger = logging.getLogger(__name__)


def cleanup_stale() -> None:
    """Clean up leftover state from a crashed mitmproxy process."""
    state = load_state()
    if state is None:
        return
    logger.info("Cleaning up stale mitmproxy process (PID %d)", state.pid)
    try:
        os.kill(state.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass  # already dead or not ours
    clear_intercept()
    clear_state()


def clear_intercept() -> None:
    """Clear the macOS local-redirect intercept so traffic flows normally.

    The mitmproxy redirector app (Network Extension) persists
    independently of the mitmdump process. If mitmdump crashes or is
    killed without a clean shutdown, the extension keeps redirecting
    traffic into a void. This connects to the existing redirector app
    and sets an empty intercept spec, restoring normal traffic flow.
    """
    import asyncio

    async def _do_clear() -> None:
        from mitmproxy_rs.local import start_local_redirector

        async def _noop(_stream: object) -> None:
            pass

        redirector = await start_local_redirector(_noop, _noop)
        redirector.set_intercept("")
        # Don't close — mitmproxy keeps the redirector app alive to avoid
        # re-triggering the macOS approval dialog on next start.

    try:
        asyncio.run(_do_clear())
        logger.info("Cleared stale mitmproxy intercept")
    except Exception:
        logger.debug("Could not clear mitmproxy intercept", exc_info=True)
