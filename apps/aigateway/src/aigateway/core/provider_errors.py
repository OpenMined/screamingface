"""Provider error types shared by core and provider plugins (OME-428 CODE-2).

Provenance matters at the retry decision: a transport failure (litellm raised
before a response existed) may be retried, but an error a plugin manufactures
from an already-returned response body means the upstream call happened — and
may already be billed — so it must never trigger another upstream call.
"""

from __future__ import annotations

from fastapi import HTTPException


class NonRetryableProviderError(HTTPException):
    """An error manufactured from an already-returned upstream response.

    # WHY: plugins detect provider failures embedded in nominal HTTP-200
    # bodies (e.g. OpenRouter's in-body 429). Raising a plain HTTPException
    # with a retryable status would re-enter the overload-retry loop and
    # re-dispatch a call that already completed upstream.
    # INVARIANT: subclasses HTTPException so the routes' dispatch-failure
    # path (credential marking, error rendering) is unchanged; only the
    # retry predicate reads the marker.
    """

    # Read duck-typed by core.retry.is_retryable_status — retry.py stays
    # stdlib-only by never importing this (fastapi-backed) module.
    aigw_non_retryable = True
