"""Log configuration for both modes of the image.

WHY this module exists at all: `uvicorn.run()` installs handlers for the
`uvicorn*` loggers ONLY and leaves the root logger with none. Every
`screamingface_engine` record therefore fell through to `logging.lastResort`, which
emits at WARNING — so the App's INFO lines were discarded in every deployment that
has ever run. The visible symptom was a control plane whose logs contained nothing
but `uvicorn.access` health checks, which reads as "nothing happened" rather than
"this process cannot say anything".

That mattered most for exactly the evidence hardest to get any other way: the WebSocket
close code. Only the App observes it — a client cannot report a close it never received —
and a dropped Run stream is otherwise indistinguishable from every other dropped Run stream.

Stdlib only, deliberately: the run mode (a Job) needs this as much as the serving mode, and
the layering rule keeps the two import graphs disjoint.
"""

import logging
import os
from typing import TextIO

APP_LOGGER = "screamingface_engine"
LEVEL_ENV = "URL4_CLOUD_LOG_LEVEL"
DEFAULT_LEVEL = "INFO"

# Matches uvicorn's own column so a deployment's logs read as one stream rather than two.
_FORMAT = "%(levelname)s:     %(name)s %(message)s"

_INSTALLED = "_screamingface_engine_log_handler"
"""Marks the handler THIS module installed.

Idempotence has to be about our own handler, not about the logger being empty: anything
else may have attached one first — a test harness, a sidecar, an embedding process — and
`if not logger.handlers` would then read that as "already configured" and install nothing
at all. The failure is silent and looks exactly like the bug this module exists to fix.
"""


def configure(stream: TextIO | None = None) -> None:
    """Give the `screamingface_engine` logger tree its own handler and level.

    Idempotent: a second call neither stacks handlers nor disturbs anyone else's.
    `propagate` is disabled so that a later root configuration — uvicorn's, a test
    harness's, a sidecar's — cannot turn every record into two.
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
