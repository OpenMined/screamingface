from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core.profile_index import ProfileIndexStore

router = APIRouter()


def _index_store(request: Request) -> ProfileIndexStore:
    return request.app.state.profile_index


@router.get("/v1/auth/profiles")
async def list_profiles(request: Request) -> dict:
    idx = await _index_store(request).read()
    return {"profiles": [p.model_dump(mode="json") for p in idx.profiles]}


@router.get("/v1/auth/{provider}/profiles")
async def list_provider_profiles(provider: str, request: Request) -> dict:
    idx = await _index_store(request).read()
    return {
        "profiles": [
            p.model_dump(mode="json") for p in idx.profiles if p.provider == provider
        ]
    }


@router.get("/v1/auth/{provider}/profiles/{name}")
async def get_profile(provider: str, name: str, request: Request) -> dict:
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "profile_not_found", "provider": provider, "name": name},
        )
    return p.model_dump(mode="json")
