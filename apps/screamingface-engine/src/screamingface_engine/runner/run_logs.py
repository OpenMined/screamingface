"""Generic run-scoped structured Log interface and local validation."""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Literal

from screamingface_engine.run_log_contract import (
    LogScalar,
    RunLogScopeFactory,
    StructuredLogEmitter,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StructuredLog:
    """One validated Runner-local input for an ordinary root Log frame."""

    body: str
    attributes: dict[str, LogScalar]


class RunLogEmitter:
    """Validate, snapshot, and synchronously submit Logs while one scope is alive.

    WHY this implementation sits behind ``StructuredLogEmitter``: producers should learn only
    ``emit(body, attributes)``. Validation, expiry, diagnostics, and bridge input ownership remain
    local to the Runner adapter and cannot be inconsistently recreated by every producer.
    """

    __slots__ = (
        "_active",
        "_expired_warned",
        "_owner_thread_id",
        "_submit",
    )

    def __init__(self, submit: Callable[[StructuredLog], None]) -> None:
        self._submit = submit
        self._owner_thread_id = threading.get_ident()
        self._active = True
        self._expired_warned = False

    def __call__(self, body: str, attributes: Mapping[str, LogScalar]) -> None:
        # INVARIANT: `_Bridge` owns an asyncio.Event and a deque with no cross-thread
        # synchronization. Reject at this outer seam before any of that state can be touched.
        if threading.get_ident() != self._owner_thread_id:
            _logger.warning("run Log off-thread submission ignored")
            return
        if not self._active:
            if not self._expired_warned:
                _logger.warning("run Log expired emitter ignored")
                self._expired_warned = True
            return
        record = self._validate(body, attributes)
        if record is None:
            return
        try:
            self._submit(record)
        except Exception as exc:  # noqa: BLE001 - this observational seam is fail-open by contract
            _logger.warning(
                "run Log submission failed (%s)",
                type(exc).__name__,
            )

    def close(self) -> None:
        self._active = False

    @staticmethod
    def _validate(body: object, attributes: object) -> StructuredLog | None:
        try:
            if type(body) is not str or not body or not isinstance(attributes, Mapping):
                raise _InvalidStructuredLog
            snapshot: dict[str, LogScalar] = {}
            for key, value in attributes.items():
                # INVARIANT: exact built-in scalar types and finite floats only. Pydantic coercion
                # would turn a producer defect into a plausible-looking wire claim; its JSON
                # encoder also rewrites nan and infinities to null, erasing their original meaning.
                if (
                    type(key) is not str
                    or (value is not None and type(value) not in {str, int, float, bool})
                    or (type(value) is float and not math.isfinite(value))
                ):
                    raise _InvalidStructuredLog
                snapshot[key] = value
        except _InvalidStructuredLog:
            _logger.warning("run Log submission rejected")
        except Exception as exc:  # noqa: BLE001 - hostile Mapping implementations are input here
            _logger.warning("run Log submission rejected (%s)", type(exc).__name__)
        else:
            return StructuredLog(body=body, attributes=snapshot)
        return None


class _InvalidStructuredLog(ValueError):
    """Internal control flow for a record outside the flat scalar contract."""


class RunLogScope(AbstractContextManager[None]):
    """Contain one optional adapter scope without exposing lifecycle complexity to Runner."""

    __slots__ = ("_emitter", "_factory", "_inner", "_rendered_url4")

    def __init__(
        self,
        factory: RunLogScopeFactory | None,
        rendered_url4: str,
        submit: Callable[[StructuredLog], None],
    ) -> None:
        self._factory = factory
        self._rendered_url4 = rendered_url4
        self._emitter = RunLogEmitter(submit)
        self._inner: AbstractContextManager[None] | None = None

    def __enter__(self) -> None:
        inner = self._open()
        if inner is not None:
            try:
                inner.__enter__()
            except Exception as exc:  # noqa: BLE001 - observational entry is fail-open
                _log_scope_failure("entry", exc)
            else:
                self._inner = inner
                return
        self._emitter.close()

    def _open(self) -> AbstractContextManager[None] | None:
        if self._factory is None:
            return None
        try:
            return self._factory.open_run_scope(self._rendered_url4, self._emitter)
        except Exception as exc:  # noqa: BLE001 - observational setup is fail-open
            _log_scope_failure("setup", exc)
            return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            if self._inner is not None:
                try:
                    self._inner.__exit__(exc_type, exc_value, traceback)
                except Exception as exc:  # noqa: BLE001 - observational teardown is fail-open
                    _log_scope_failure("teardown", exc)
        finally:
            # INVARIANT: teardown may emit its last record; expiry happens only AFTER exit.
            self._emitter.close()
        # An observational adapter can neither suppress nor replace execution failure.
        return False


def _log_scope_failure(phase: str, error: Exception) -> None:
    # INVARIANT: URL4 and Log payloads can contain private Benchmark material. Diagnostics name
    # only the stable seam phase and exception class; exception messages are never interpolated.
    _logger.warning("run Log scope %s failed (%s)", phase, type(error).__name__)


__all__ = [
    "LogScalar",
    "RunLogEmitter",
    "RunLogScope",
    "RunLogScopeFactory",
    "StructuredLog",
    "StructuredLogEmitter",
]
