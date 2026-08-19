"""Tests for the aigateway app-logger configuration.

WHY this exists: ``uvicorn.run()`` installs handlers for the ``uvicorn*``
loggers only. Without our own configuration every ``aigateway.*`` record
falls through to ``logging.lastResort``, which emits at WARNING — so all
INFO-level operational evidence (e.g. the per-provider concurrency limit,
OME-889) was silently discarded in every real deployment.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator

import pytest

from aigateway import logs
from aigateway.core.concurrency import provider_slot


def _detach_installed_handlers() -> None:
    logger = logging.getLogger(logs.APP_LOGGER)
    for handler in list(logger.handlers):
        if getattr(handler, logs._INSTALLED, False):
            logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


@pytest.fixture(autouse=True)
def _reset_app_logger() -> Iterator[None]:
    """Detach handlers this module installed — BEFORE each test too: any earlier
    test that built the app via ``create_app()`` already ran ``configure()``,
    and the idempotence guard would then (correctly) refuse to install this
    test's stream handler."""
    _detach_installed_handlers()
    yield
    _detach_installed_handlers()


def test_configure_makes_info_records_visible() -> None:
    """INVARIANT: an INFO record from any aigateway.* module reaches the
    stream — the exact failure mode being fixed is INFO falling through to
    lastResort (WARNING+) and vanishing."""
    stream = io.StringIO()
    logs.configure(stream)
    logging.getLogger("aigateway.core.concurrency").info("hello info=1")
    assert "hello info=1" in stream.getvalue()


def test_configure_level_env_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(logs.LEVEL_ENV, "WARNING")
    stream = io.StringIO()
    logs.configure(stream)
    logging.getLogger("aigateway.core.concurrency").info("quiet info")
    assert stream.getvalue() == ""


def test_configure_is_idempotent() -> None:
    """INVARIANT: a second configure (create_app called twice, tests) must not
    stack handlers and double every log line."""
    stream = io.StringIO()
    logs.configure(stream)
    logs.configure(stream)
    logging.getLogger(logs.APP_LOGGER).info("once")
    assert stream.getvalue().count("once") == 1


def test_configure_disables_propagation() -> None:
    """A later root/uvicorn configuration must not duplicate our records."""
    logs.configure(io.StringIO())
    assert logging.getLogger(logs.APP_LOGGER).propagate is False


# STORY: as an operator tailing aigateway.log after OME-889, the first
# OpenRouter call must actually print the limit in force — this is the
# end-to-end proof caplog-based tests could not give.
@pytest.mark.asyncio
async def test_concurrency_limit_line_reaches_configured_stream() -> None:
    from types import SimpleNamespace

    stream = io.StringIO()
    logs.configure(stream)
    app = SimpleNamespace(state=SimpleNamespace())
    async with provider_slot(app, "openrouter", 32):
        pass
    assert "provider concurrency limit applied provider=openrouter limit=32" in stream.getvalue()
