"""Delivery of panel background completions, independent of notebook loop churn."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class _CompletionDispatcher:
    """Runs a panel's background completions whatever became of the rendering loop.

    INVARIANT: a dispatched callback ALWAYS runs. Discarding a completion because no
    event loop would accept it is what stranded ``sf.connect()`` on "checking" forever
    in Colab (OME-926) — the worker had the answer in hand and threw it away.

    AIDEV-NOTE: this is the single completion-dispatch mechanism for the connection
    panel. Never reintroduce a bare ``except RuntimeError: return`` around
    ``call_soon_threadsafe`` at a call site; route the completion through here instead.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """The loop completions are currently posted to, or None to run them inline."""

        return self._loop

    def capture(self) -> None:
        """Adopt the loop live on this thread — called when the panel renders."""

        self._loop = self.running_loop()

    def adopt(self, loop: asyncio.AbstractEventLoop) -> None:
        """Adopt a loop resolved by a caller that already knows the live one."""

        self._loop = loop

    def usable(self) -> asyncio.AbstractEventLoop | None:
        """The loop that should take a completion now, or None to run it inline.

        WHY: a notebook host may close OR silently replace the loop that was live when
        the widget rendered, and an abandoned loop accepts ``call_soon_threadsafe``
        without ever running the callback. Requiring ``is_running()`` rejects both the
        closed and the abandoned loop, so the only loops we post to are ones that will
        actually drain the callback.
        """

        for candidate in (self.running_loop(), self._loop):
            if candidate is not None and not candidate.is_closed() and candidate.is_running():
                return candidate
        return None

    def __call__(self, callback: Callable[..., None], *args: Any) -> None:
        """Deliver ``callback`` — via a live loop where there is one, else inline."""

        loop = self.usable()
        if loop is None:
            callback(*args)
            return
        try:
            loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            # WHY: the loop can pass the checks above and still reject the post — it may
            # close in that window. Running inline keeps the panel truthful.
            callback(*args)
        # AIDEV-NOTE: deliberately does NOT adopt `loop`. usable() re-resolves a running
        # loop on every call, so the latch bought nothing — and a completion arriving from
        # a thread that owns an unrelated running loop would have aimed every later widget
        # mutation at that foreign loop. Post to a loop; never attach to it.

    @staticmethod
    def running_loop() -> asyncio.AbstractEventLoop | None:
        """The loop running on the calling thread, or None.

        Named on the surface because callers also need to ask whether they may schedule
        work at all rather than block.
        """

        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None


__all__: list[str] = []
