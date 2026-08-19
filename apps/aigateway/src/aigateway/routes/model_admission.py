"""``POST /v1/models/admit`` — dynamic model admission (OME-879).

FEATURE: run any OpenRouter model (OME-878). The url4-cloud engine calls this
endpoint on a model-id miss: "does this model actually exist?" A grant
registers the model live — it joins ``GET /v1/models`` and resolves on
``GET /v1/model-parameters`` for the rest of this deployment's life. A refusal
is a 200 ANSWER carrying a diagnostic code, never an HTTP error: the caller's
next move (tell the user which knob to turn) needs the body either way.

STORY: as a researcher, I point a run at any real OpenRouter model and it just
works with only my OpenRouter key; typos refuse before any money is spent.

INVARIANT: admission state lives on ``app.state`` only — nothing persists, a
restart forgets every admission, and re-admission is idempotent.
INVARIANT (hexagonal): this core route knows no provider. The decision is the
plugin's ``admit_model`` port; core contributes only the account-scoped
credential verdict, which is core's own vocabulary (profiles/connections).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.auth.middleware import CurrentAccount
from ..core.model_capabilities import canonical_model_id
from .chat_credentials import _credential_target_for_chat

router = APIRouter()

# WHY a cap (review F7): the admitted set has no eviction, so without a ceiling a
# runaway loop could grow every tenant's `GET /v1/models` and every scheduled run's
# env without bound. The value sits ABOVE OpenRouter's whole public catalog (~415
# models as of 2026-08-19), so no legitimate use — even "admit everything" — ever
# hits it; it exists purely as a backstop against catalog growth and abuse, and
# stays far below the discovery parser's 10k document ceiling. A real teardown
# story (LRU/TTL/admin delete) is a follow-up design decision, not invented here.
_MAX_ADMITTED_MODELS = 1024


class _AdmitRequest(BaseModel):
    model_id: str


def _answer(model_id: str, *, admitted: bool, code: str | None, message: str | None) -> dict:
    return {
        "object": "model.admission",
        "model_id": model_id,
        "admitted": admitted,
        "code": code,
        "message": message,
    }


def _capacity_refusal(model_id: str) -> dict:
    return _answer(
        model_id,
        admitted=False,
        code="admission_capacity_reached",
        message=(
            f"this deployment has dynamically admitted {_MAX_ADMITTED_MODELS} models, "
            "its capacity — seed the model statically (AIGW_OPENROUTER_DEFAULT_MODELS) "
            "or restart the gateway to clear dynamic admissions"
        ),
    )


def _store_admission(admitted_models: dict[str, Any], model_id: str, entry: Any) -> bool:
    """Insert under the cap — the DEFINITIVE enforcement point.

    WHY here and not only at the top of the route: between the route's cheap
    pre-check and this insert sit two awaits (credential resolution and the
    catalog dial). Concurrent admissions interleave at those awaits, so N
    requests could all pass a pre-check taken at ``len == cap - 1`` and then all
    insert, overshooting the cap. This function has NO awaits between its check
    and its insert, which under asyncio's single-threaded loop makes the pair
    atomic — the pre-check is a cost optimization, this is the law.

    An id a rival admitted during the window is a grant (idempotence outranks
    the cap, exactly like the route's known-model short-circuit).
    """
    if model_id in admitted_models:
        return True
    if len(admitted_models) >= _MAX_ADMITTED_MODELS:
        return False
    admitted_models[model_id] = entry
    return True


async def _credential_verdict(
    request: Request, *, account_id: str, provider: str, plugin: Any
) -> tuple[bool, tuple[str, str] | None]:
    """(credentialed, relayed refusal) for the calling account on ``provider``.

    Reuses the chat path's credential resolution verbatim so admission and
    dispatch cannot disagree about what "credentialed" means. A profile that
    EXISTS but is in a reauth/pending state is not "no key" (review F6): those
    two states are relayed as their own (code, message) so the user is told to
    finish or redo the connection — not to re-add a key they already have. Every
    other refusal (typically a missing profile) collapses to plain
    not-credentialed, and the plugin's ladder words that diagnosis.
    """
    profile_name = (request.headers.get("X-Profile") or "default").strip() or "default"
    try:
        profile, connection, _defaults = await _credential_target_for_chat(
            request,
            account_id=account_id,
            provider=provider,
            profile_name=profile_name,
            plugin=plugin,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, Mapping) else {}
        code = detail.get("code")
        if code == "auth_required":
            return False, (
                "auth_required",
                f"the {provider} profile {profile_name!r} must be reconnected — "
                "reauthorize it, then retry",
            )
        if code == "profile_pending_auth":
            return False, (
                "profile_pending_auth",
                f"the {provider} profile {profile_name!r} is still connecting — "
                "finish the connection, then retry",
            )
        return False, None
    return (profile is not None or connection is not None), None


@router.post("/v1/models/admit")
async def admit_model(request: Request, current: CurrentAccount, body: _AdmitRequest) -> dict:
    model_id = body.model_id
    provider = model_id.split("/", 1)[0] if "/" in model_id else ""
    plugin = request.app.state.providers.get(provider)
    if plugin is None:
        return _answer(
            model_id,
            admitted=False,
            code="unknown_provider",
            message=f"unknown provider: {provider!r}",
        )

    # Idempotence, cheapest first: an id already served (seeded or previously
    # admitted) is a grant with zero upstream work — this is what lets a saved
    # notebook re-admit after a gateway restart without a visible difference.
    known = {
        canonical_model_id(custom_llm_provider=provider, model_name=entry.model_name)
        for entry in plugin.register_models()
    }
    admitted_models: dict[str, Any] = request.app.state.admitted_models
    if model_id in known or model_id in admitted_models:
        return _answer(model_id, admitted=True, code=None, message=None)

    # Capacity before any credential or catalog work (review F7): a full set is a
    # refusal that must cost nothing. This pre-check is NOT the enforcement —
    # `_store_admission` below is; awaits sit between here and the insert.
    if len(admitted_models) >= _MAX_ADMITTED_MODELS:
        return _capacity_refusal(model_id)

    credentialed, relayed = await _credential_verdict(
        request, account_id=str(current.id), provider=provider, plugin=plugin
    )
    if relayed is not None:
        code, message = relayed
        return _answer(model_id, admitted=False, code=code, message=message)
    runtime = request.app.state.discovery_runtime
    decision = await plugin.admit_model(
        model_id,
        discovery_client=runtime.client if runtime is not None else None,
        discovery_limits=runtime.limits if runtime is not None else None,
        # Per-provider compartment (review F9): plugins write generic keys
        # ("ids"/"expires_at"), so handing every provider the same flat dict would
        # let the second `admit_model` implementer read OpenRouter's catalog as
        # its own — and vice versa.
        catalog_cache=request.app.state.admission_catalog_cache.setdefault(provider, {}),
        credentialed=credentialed,
    )
    if not decision.admitted or decision.entry is None:
        return _answer(model_id, admitted=False, code=decision.code, message=decision.message)
    if not _store_admission(admitted_models, model_id, decision.entry):
        # A rival admission filled the last slot while this one was at the dial.
        return _capacity_refusal(model_id)
    return _answer(model_id, admitted=True, code=None, message=None)
