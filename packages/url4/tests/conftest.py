"""Shared test fixtures and helpers."""

from __future__ import annotations

from url4 import IOLayer, StaticIOLayer
from url4.errors import ResolutionError


class RecordingIOLayer:
    """An :class:`~url4.IOLayer` that records and serves every fetch (no network).

    Delegates to a :class:`~url4.StaticIOLayer` (``fetch_map`` for static reads,
    ``routes`` for localhost ``?q=`` expression endpoints), echoes ``"<target>"``
    for anything unmapped, and appends every fetched ``target`` to :attr:`fetches`
    so tests can assert dispatch order and the encoded ``?q=`` payloads.
    """

    def __init__(self, fetch_map: dict[str, str] | None = None, routes: dict | None = None) -> None:
        self._static = StaticIOLayer(fetch_map, routes)
        self.fetches: list[str] = []

    async def fetch(self, target: str, *, relative: bool) -> str:
        self.fetches.append(target)
        try:
            return await self._static.fetch(target, relative=relative)
        except ResolutionError:
            return f"<{target}>"

    def default_route(self) -> str | None:
        """Delegate SupportsDefaultRoute — first declared route, like the static layer."""
        return self._static.default_route()


# Structural check that the helper satisfies the port.
_: IOLayer = RecordingIOLayer()
