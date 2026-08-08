"""One lazily constructed synchronous module-level Client."""

from __future__ import annotations

import os
from threading import Lock
from typing import TYPE_CHECKING, Literal, overload

from screamingface.client import DEFAULT_ENGINE_URL, Client

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from screamingface._ui.connections import ConnectionPanel
    from screamingface.connections import Connection, OAuthFlow
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


def configure(*, engine_url: str) -> Client:
    """Replace the process-wide Client used by module-level convenience functions."""

    global _client
    replacement = Client(engine_url=engine_url)
    with _lock:
        previous = _client
        _client = replacement
    if previous is not None:
        previous.close()
    return replacement


def close() -> None:
    """Close and forget the process-wide Client, if it has been created."""

    global _client
    with _lock:
        previous = _client
        _client = None
    if previous is not None:
        previous.close()


def evaluate(
    candidates: Recipe | Sequence[Recipe],
    *,
    benchmark: str,
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
    method: None = None,
) -> ConnectionPanel: ...


@overload
def connect(
    provider: str,
    *,
    api_key: str,
    method: Literal["api_key"] | None = None,
) -> Connection: ...


@overload
def connect(
    provider: str,
    *,
    api_key: None = None,
    method: Literal["oauth"],
) -> OAuthFlow: ...


def connect(
    provider: str | None = None,
    *,
    api_key: str | None = None,
    method: Literal["api_key", "oauth"] | None = None,
) -> Connection | ConnectionPanel | OAuthFlow:
    """Open the provider panel or connect through the lazy default Client."""

    if provider is None:
        if api_key is not None or method is not None:
            raise TypeError("provider is required when api_key or method is supplied")
        from screamingface._ui.connections import ConnectionPanel

        return ConnectionPanel(default_client())
    client = default_client()
    if api_key is not None:
        if method == "oauth":
            raise ValueError("api_key cannot be combined with OAuth")
        result = client.connect(provider, api_key=api_key, method=method)
    elif method == "api_key":
        raise ValueError("api_key is required for API-key authentication")
    elif method == "oauth":
        result = client.connect(provider, method="oauth")
    else:
        raise ValueError("api_key is required unless method='oauth' is selected")
    return result


def disconnect(provider: str) -> Connection:
    """Disconnect a provider through the lazy default Client."""

    return default_client().disconnect(provider)


__all__ = ["close", "configure", "connect", "disconnect", "evaluate"]
