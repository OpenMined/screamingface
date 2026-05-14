from __future__ import annotations

from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aigateway.core.auth.middleware import CurrentAccount
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileState, profile_id_for

from .auth import CodexOAuth, resolve_codex_auth_path

router = APIRouter()


class ImportProfileRequest(BaseModel):
    name: str = "default"
    defaults: ProfileDefaults | None = None


@router.post("/profiles/import", status_code=201)
async def import_profile(
    body: ImportProfileRequest, request: Request, current: CurrentAccount
) -> dict:
    account_id = str(current.id)
    strategy = CodexOAuth(profile_name=body.name, auth_file=resolve_codex_auth_path())
    try:
        creds = strategy._read_credential()
    except CredentialNotFoundError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "auth_required", "message": str(exc)},
        ) from exc
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "auth_required",
                "message": str(exc),
                "reauth_url": "/v1/auth/codex/profiles/import",
            },
        ) from exc

    profile = Profile(
        id=profile_id_for(account_id, "codex", body.name),
        account_id=account_id,
        provider="codex",
        name=body.name,
        account_label=account_label_from_claims(creds.get("id_token")),
        state=ProfileState.AUTHENTICATED,
        defaults=body.defaults or ProfileDefaults(),
    )
    await request.app.state.profile_index.upsert(profile)
    return profile.model_dump(mode="json")


def account_label_from_claims(id_token: Any) -> str | None:
    if not isinstance(id_token, str) or not id_token:
        return None
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False})
    except Exception:
        return None
    for key in ("email", "name", "https://api.openai.com/auth.chatgpt_account_id"):
        value = claims.get(key)
        if isinstance(value, str) and value:
            return value
    return None
