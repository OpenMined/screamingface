"""GET /v1/model-parameters — profile-bound detailed parameter contract (OME-479).

The client sends the same gateway auth + ``X-Profile`` it will use for chat. This
route REUSES the chat credential-target resolution and derives the auth mode from
the stored profile/connection; it never accepts a caller-declared auth type,
credential, or provider origin. The provider is selected by the canonical model
prefix (a unique registry key), and the response is per-account/profile —
``private, no-store`` and varying by authorization + profile.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from ..core.auth.middleware import CurrentAccount
from ..core.model_capabilities import canonical_model_id
from ..core.model_parameter_contract import build_model_parameter_document
from ..core.registry import ProviderRegistry
from .chat_credentials import _credential_target_for_chat, auth_mode_for_target

if TYPE_CHECKING:
    from ..core.oauth.models import OAuthConnection
    from ..core.profile_models import Profile

router = APIRouter()

# Local/labelled evidence in v1 is not a time-bounded remote observation, so it
# carries no observed_at/expires_at window; discovery freshness arrives later.
_LOCAL_FRESHNESS: dict[str, Any] = {"stale": False, "degraded": False}


def _context_identity(
    account_id: str,
    profile: Profile | None,
    connection: OAuthConnection | None,
) -> str:
    """Opaque, NON-secret digest input: account + selected target + its state.

    Folded into the one-way contract/context digests so the ids change when the
    selected profile/connection or its generation/state changes. Never echoed.
    """
    if connection is not None:
        target = f"conn:{connection.id}:{connection.status}:{connection.last_refreshed_at or '-'}"
    elif profile is not None:
        target = f"prof:{profile.id}:{profile.state.value}:{profile.last_refreshed_at or '-'}"
    else:
        target = "anon"
    return f"acct:{account_id}|{target}"


@router.get("/v1/model-parameters")
async def model_parameters(
    request: Request,
    response: Response,
    current: CurrentAccount,
    model: Annotated[str, Query()],
) -> dict[str, Any]:
    provider = model.split("/", 1)[0] if "/" in model else None
    if not provider:
        raise HTTPException(status_code=400, detail="model must be provider-prefixed")

    registry: ProviderRegistry = request.app.state.providers
    plugin = registry.get(provider)
    if plugin is None:
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider}")

    # Canonical-id lookup BEFORE any profile work: reject unknown/cross-provider
    # ids (an id owned by another plugin is simply not in this plugin's set).
    known = {
        canonical_model_id(custom_llm_provider=provider, model_name=entry.model_name)
        for entry in plugin.register_models()
    }
    if model not in known:
        raise HTTPException(
            status_code=404,
            detail={"code": "model_not_found", "provider": provider, "model": model},
        )

    profile_name = (request.headers.get("X-Profile") or "default").strip() or "default"
    account_id = str(current.id)
    # Reuse the chat resolution verbatim (raises the same 404/409 on a missing/
    # pending/errored profile) so summary, detail, and dispatch agree on context.
    profile, connection, _defaults = await _credential_target_for_chat(
        request,
        account_id=account_id,
        provider=provider,
        profile_name=profile_name,
        plugin=plugin,
    )
    auth_mode = auth_mode_for_target(profile, connection)

    document = build_model_parameter_document(
        canonical_id=model,
        gateway_provider=provider,
        auth_mode=auth_mode,
        scope="account_profile",
        context_identity=_context_identity(account_id, profile, connection),
        rules=plugin.chat_parameter_rules(model=model, auth_type=auth_mode),
        observations=plugin.chat_parameter_observations(model=model, auth_type=auth_mode),
        tools=plugin.chat_parameter_tools(model=model, auth_type=auth_mode),
        transport=plugin.chat_transport_capabilities(model=model, auth_type=auth_mode),
        freshness=dict(_LOCAL_FRESHNESS),
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization, X-Profile"
    return document
