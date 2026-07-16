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
_LOCAL_ENGINE = "http://127.0.0.1:4404"


@dataclass
class Session:
    mode: Mode = "mock"
    engine_url: str = _LOCAL_ENGINE
    static_widgets: bool = False
    dataset_source: str = "synthetic-gpqa-shaped"
    engine: EnginePort | None = field(default=None, repr=False, compare=False)
    closed: bool = field(default=False, init=False)

    def _repr_html_(self) -> str:
        label = "SIMULATED" if self.mode == "mock" else "LIVE DATASET"
        return (
            "<div><strong>ScreamingFace</strong> "
            f"<code>{label}</code><br>URL4 engine: {self.engine_url}</div>"
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
    """Configure the URL4 engine and dataset mode; calling this is optional."""
    if mode not in ("live", "mock"):
        raise ValueError("mode must be 'live' or 'mock'")
    dataset_source = (
        "synthetic-gpqa-shaped" if mode == "mock" else "gated:Idavidrein/gpqa:gpqa_diamond"
    )
    session = Session(
        mode=mode,
        engine_url=engine or os.getenv("SCREAMINGFACE_ENGINE_URL") or _LOCAL_ENGINE,
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
