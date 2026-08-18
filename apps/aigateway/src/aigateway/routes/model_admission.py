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

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.auth.middleware import CurrentAccount
from ..core.model_capabilities import canonical_model_id
from .chat_credentials import _credential_target_for_chat

router = APIRouter()


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


async def _is_credentialed(
    request: Request, *, account_id: str, provider: str, plugin: Any
) -> bool:
    """True when the calling account can actually dispatch to ``provider``.

    Reuses the chat path's credential resolution verbatim so admission and
    dispatch cannot disagree about what "credentialed" means; its refusal
    exceptions (missing/pending/errored profile) all collapse to False here —
    the admission answer carries the diagnostic instead.
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
    except HTTPException:
        return False
    return profile is not None or connection is not None


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

    credentialed = await _is_credentialed(
        request, account_id=str(current.id), provider=provider, plugin=plugin
    )
    runtime = request.app.state.discovery_runtime
    decision = await plugin.admit_model(
        model_id,
        discovery_client=runtime.client if runtime is not None else None,
        discovery_limits=runtime.limits if runtime is not None else None,
        catalog_cache=request.app.state.admission_catalog_cache,
        credentialed=credentialed,
    )
    if not decision.admitted or decision.entry is None:
        return _answer(model_id, admitted=False, code=decision.code, message=decision.message)
    admitted_models[model_id] = decision.entry
    return _answer(model_id, admitted=True, code=None, message=None)
