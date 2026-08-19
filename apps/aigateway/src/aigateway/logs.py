"""Log configuration for the aigateway app logger tree.

WHY this module exists: ``uvicorn.run()`` installs handlers for the
``uvicorn*`` loggers ONLY and leaves the root logger with none. Every
``aigateway.*`` record therefore fell through to ``logging.lastResort``,
which emits at WARNING — so the gateway's INFO lines were discarded in every
deployment that has ever run. Found via OME-889: the per-provider concurrency
limit line (the operator's only proof of which limit is in force) never
appeared in the stack log.

Same defect, same cure as the Engine's ``screamingface_engine/logs.py`` —
mirrored rather than shared because apps must not import each other's
internals (a 30-line stdlib module does not justify a shared package).
"""

from __future__ import annotations

import logging
import os
from typing import TextIO

APP_LOGGER = "aigateway"
LEVEL_ENV = "AIGW_LOG_LEVEL"
DEFAULT_LEVEL = "INFO"

# Matches uvicorn's own column so a deployment's logs read as one stream rather than two.
_FORMAT = "%(levelname)s:     %(name)s %(message)s"

_INSTALLED = "_aigateway_log_handler"
"""Marks the handler THIS module installed.

Idempotence has to be about our own handler, not about the logger being empty:
anything else may have attached one first — a test harness, a sidecar, an
embedding process — and ``if not logger.handlers`` would then read that as
"already configured" and install nothing at all. The failure is silent and
looks exactly like the bug this module exists to fix.
"""


def configure(stream: TextIO | None = None) -> None:
    """Give the ``aigateway`` logger tree its own handler and level.

    Idempotent: a second call neither stacks handlers nor disturbs anyone
    else's. ``propagate`` is disabled so that a later root configuration —
    uvicorn's, a test harness's, a sidecar's — cannot turn every record into
    two.
    """

    logger = logging.getLogger(APP_LOGGER)
    logger.setLevel(os.getenv(LEVEL_ENV, DEFAULT_LEVEL).upper())
    if not any(getattr(handler, _INSTALLED, False) for handler in logger.handlers):
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(_FORMAT))
        setattr(handler, _INSTALLED, True)
        logger.addHandler(handler)
    logger.propagate = False


__all__ = ["APP_LOGGER", "DEFAULT_LEVEL", "LEVEL_ENV", "configure"]
