"""One lazily constructed synchronous module-level Client."""

from __future__ import annotations

import os
from threading import Lock
from typing import TYPE_CHECKING, overload

from screamingface.client import DEFAULT_ENGINE_URL, Client

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from screamingface._ui.connections import ConnectionPanel
    from screamingface.connections import Connection
    from screamingface.events import Event
    from screamingface.recipe import Recipe
    from screamingface.report import Report

_client: Client | None = None
_lock = Lock()


def default_client() -> Client:
    """Return the process-wide Client, constructing it on first use."""

    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is None:
            _client = Client(
                engine_url=os.environ.get("SCREAMINGFACE_ENGINE_URL", DEFAULT_ENGINE_URL)
            )
    return _client


def evaluate(
    candidates: Recipe | Sequence[Recipe],
    *,
    benchmark: str | None = None,
    limit: int | None = None,
    on_event: Callable[[Event], None] | None = None,
    progress: bool | None = None,
) -> Report:
    """Evaluate Candidates through the lazily constructed default Client."""

    return default_client().evaluate(
        candidates,
        benchmark=benchmark,
        limit=limit,
        on_event=on_event,
        progress=progress,
    )


@overload
def connect(
    provider: None = None,
    *,
    api_key: None = None,
) -> ConnectionPanel: ...


@overload
def connect(
    provider: str,
    *,
    api_key: str,
) -> Connection: ...


def connect(
    provider: str | None = None,
    *,
    api_key: str | None = None,
) -> Connection | ConnectionPanel:
    """Open the provider panel or connect through the lazy default Client."""

    if provider is None:
        if api_key is not None:
            raise TypeError("provider is required when api_key is supplied")
        from screamingface._ui.connections import ConnectionPanel

        return ConnectionPanel(default_client())
    if api_key is None:
        raise ValueError("api_key is required when connecting a provider")
    return default_client().connect(provider, api_key=api_key)


def disconnect(provider: str) -> Connection:
    """Disconnect a provider through the lazy default Client."""

    return default_client().disconnect(provider)


__all__ = ["connect", "disconnect", "evaluate"]
