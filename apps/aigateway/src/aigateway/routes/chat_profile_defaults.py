"""Profile defaults at the chat route: what enters the KEY, and who is BLAMED.

Both members here exist for the same reason — a stored profile default is merged into
the caller's request and then travels through the gateway as if the caller had sent
it. ``profile_defaults_for_key`` puts those values inside the global cache key
(OME-305 §57); ``_parameter_rejection_exception`` attributes a classification failure
back to the profile that really caused it (OME-638). Split out of ``routes/chat.py``,
which was at its size limit.

FEATURE: one globally shared exact-request cache, keyed on the EFFECTIVE request,
plus one parameter contract that treats a stored default exactly like a sent value.

STORY: as an operator I keep a per-profile ``system_prompt`` so my callers can send a
bare body. The cache must treat my two profiles' bare bodies as the two DIFFERENT
requests they really are, while still sharing a row with anyone whose request happens
to be identical once defaults are applied.

AIDEV-NOTE: deliberately NOT in ``chat_credentials``. That module resolves a
dispatchable credential and does so by RAISING — 404 ``profile_not_found``, 409
``profile_pending_auth``, 401 ``auth_required``. The read below runs BEFORE the cache
lookup, where any of those raises would refuse a request the cache could have served.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from ..core.parameter_projection import UnsupportedParametersError
from ..core.profile_index import ProfileIndexStore
from ..core.profile_models import ProfileDefaults

logger = logging.getLogger(__name__)


async def profile_defaults_for_key(
    request: Request,
    *,
    account_id: str,
    provider: str,
    profile_name: str,
) -> ProfileDefaults | None:
    """Read ONLY this caller's stored defaults, before any credential is resolved.

    OME-305 ruling 57: ``cache_behavior="keyed"`` disciplined only CALLER-SUPPLIED
    values, because the defaults merge ran after the key was built and a default fills
    only an omitted path. Two callers could both POST a bare ``{model, messages}`` and
    collide on one key while their profiles asked the provider two different questions
    — a wrong ANSWER, not a missed saving. Merging before the key closes that, and
    this is the narrowest read that makes the merge possible.

    INVARIANT: never raises, and never inspects ``ProfileState``. Its sibling
    ``_credential_target_for_chat`` raises at ``chat_credentials.py`` :185 (404), :196
    (409) and :205 (401). Put any of those ahead of the cache lookup and an absent,
    PENDING or ERRORED profile would be REFUSED where today it is SERVED from cache —
    destroying the inversion this whole ticket exists for. So this function also
    resolves no OAuth connection and consults no chatless-profile allowance; Stage 2
    still does every one of those things, unchanged.

    INVARIANT: ``None`` means the index could not be READ — never "this profile has no
    defaults", which is an empty ``ProfileDefaults``. That distinction IS the
    fail-safe: carrying on with empty defaults after a failed read would key the bare
    body and manufacture precisely the wrong-hit class ruling 57 closes. The caller
    must bypass the cache instead, and then merge the defaults Stage 2 resolves so the
    request still DISPATCHES with them.

    AIDEV-NOTE: a hit now costs one profile-index read, and that index is itself a
    ``credential_blobs`` row — so a hit performs one master-key decryption where it
    previously performed none. No provider credential is read, decrypted or injected,
    and no auth mode is resolved; that is the property the inversion needs.
    """
    idx: ProfileIndexStore = request.app.state.profile_index
    try:
        profile = await idx.get(account_id, provider, profile_name)
    except Exception:
        # WHY the broad catch: this is a fail-safe boundary, not error handling. The
        # index read decrypts and validates a stored blob, so its failure modes are
        # open-ended, and every one of them must degrade to "do not use the cache"
        # rather than fail a request the provider can serve. Same posture as the
        # availability and read guards in ``chat_cache_stage``. Nothing is swallowed:
        # the failure is logged and the return value forces the caller to bypass.
        logger.warning("profile index unreadable before the cache stage; bypassing the cache")
        return None
    return ProfileDefaults() if profile is None else profile.defaults


def _parameter_rejection_exception(
    exc: UnsupportedParametersError,
    *,
    provider: str,
    profile_name: str,
    default_paths: frozenset[str],
) -> HTTPException:
    """Render a classification failure against the source that actually caused it.

    WHY two codes (OME-638): profile defaults are classified in the SAME pass as
    caller fields, so one rejection map can mix an operator-configuration fault
    with a request fault. Reporting a stored default under
    ``unsupported_parameters`` would send the caller hunting through a request
    that does not contain the named field, so a rejection caused solely by
    defaults gets its own code and names the profile instead. 400 either way,
    matching ``api_key_not_supported`` — stored configuration this provider
    cannot serve is a bad request, not a server fault.

    INVARIANT: the caller-facing ``rejected`` map lists only paths the CALLER
    supplied. Defaults occupy only omitted paths, so the two sets are disjoint and
    neither error can echo the other's fields.

    WHY a caller fault wins when both are present: the request has to be fixed
    regardless, and it is the only half the caller can act on. The profile half is
    logged for the operator rather than dropped.
    """
    caller_rejected = {
        path: reason for path, reason in exc.rejected.items() if path not in default_paths
    }
    if caller_rejected:
        return HTTPException(
            status_code=400,
            detail={
                "code": "unsupported_parameters",
                "provider": provider,
                "rejected": caller_rejected,
                "message": (
                    "one or more parameters are not enabled for this model; "
                    "see the model parameter contract"
                ),
            },
        )
    return HTTPException(
        status_code=400,
        detail={
            "code": "invalid_profile_defaults",
            "provider": provider,
            "profile": profile_name,
            "rejected": exc.rejected,
            "message": (
                "the stored profile defaults are not enabled for this model; "
                "see the model parameter contract"
            ),
        },
    )
