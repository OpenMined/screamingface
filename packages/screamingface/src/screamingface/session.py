"""Optional URL4 engine configuration and process-local SDK state."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from screamingface.engine import EnginePort

Mode = Literal["live", "mock"]
_MOCK_ENGINE = "mock"


@dataclass
class Session:
    mode: Mode = "mock"
    engine_url: str = _MOCK_ENGINE
    static_widgets: bool = False
    dataset_source: str = "synthetic-gpqa-shaped"
    engine: EnginePort | None = field(default=None, repr=False, compare=False)
    closed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        from screamingface._mock_engine import MockUrl4Engine

        if self.engine is None and self.engine_url == _MOCK_ENGINE:
            self.engine = MockUrl4Engine()
        elif self.engine is not None and self.engine_url == _MOCK_ENGINE:
            if not isinstance(self.engine, MockUrl4Engine):
                self.engine_url = "custom"

    def _repr_html_(self) -> str:
        dataset = "synthetic fixture" if self.mode == "mock" else "live dataset"
        if self.engine_url == _MOCK_ENGINE:
            engine = "local URL4 mock"
        elif self.engine_url == "custom":
            engine = "custom URL4 client"
        else:
            engine = self.engine_url
        return (
            "<div><strong>ScreamingFace</strong><br>"
            f"Dataset: {dataset}<br>URL4 engine: {engine}</div>"
        )

    def close(self) -> None:
        self.closed = True


_active: Session | None = None
_sync_executor: ThreadPoolExecutor | None = None
_worker_loop: asyncio.AbstractEventLoop | None = None


def config(
    engine: str | None = None,
    *,
    mode: Mode = "mock",
    static_widgets: bool = False,
    engine_client: EnginePort | None = None,
) -> Session:
    """Configure execution and dataset modes; calling this is optional.

    ``engine="mock"`` selects the deterministic in-process URL4 node. A URL
    selects strict HTTP execution with no fallback if that engine is unavailable.
    """
    if mode not in ("live", "mock"):
        raise ValueError("mode must be 'live' or 'mock'")
    dataset_source = (
        "synthetic-gpqa-shaped" if mode == "mock" else "gated:Idavidrein/gpqa:gpqa_diamond"
    )
    selected_engine = (
        engine if engine is not None else os.getenv("SCREAMINGFACE_ENGINE_URL") or _MOCK_ENGINE
    )
    if not isinstance(selected_engine, str) or not selected_engine.strip():
        raise ValueError("engine must be 'mock' or a non-empty URL")
    selected_engine = selected_engine.strip()
    if selected_engine != _MOCK_ENGINE and not selected_engine.startswith(("http://", "https://")):
        raise ValueError("engine must be 'mock' or an http(s) URL")
    session = Session(
        mode=mode,
        engine_url=selected_engine,
        static_widgets=static_widgets,
        dataset_source=dataset_source,
        engine=engine_client,
    )
    return _set_active(session)


def current_session() -> Session | None:
    return _active


def require_session() -> Session:
    global _active
    if _active is None:
        _active = config()
    if _active.closed:
        raise RuntimeError("The ScreamingFace session is closed; call sf.config() to create one")
    return _active


def reset_session() -> None:
    global _active
    if _active is not None:
        _active.close()
    _active = None


def shutdown() -> None:
    """Close process-local SDK state and its synchronous async worker."""
    global _sync_executor, _worker_loop
    reset_session()
    if _sync_executor is not None:
        _sync_executor.submit(_close_worker_loop).result()
        _sync_executor.shutdown(wait=True)
    _sync_executor = None
    _worker_loop = None


def _set_active(session: Session) -> Session:
    global _active
    if _active is not None and _active is not session:
        _active.close()
    _active = session
    return session


def _in_notebook() -> bool:
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        return False
    return get_ipython() is not None


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    global _sync_executor
    if _sync_executor is None:
        _sync_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screamingface-sync")
    return _sync_executor.submit(_run_on_worker_loop, awaitable).result()


def _run_on_worker_loop[T](awaitable: Coroutine[Any, Any, T]) -> T:
    global _worker_loop
    if _worker_loop is None:
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop.run_until_complete(awaitable)


def _close_worker_loop() -> None:
    global _worker_loop
    if _worker_loop is not None:
        _worker_loop.close()
        _worker_loop = None
