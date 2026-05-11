"""Anthropic bootstrap helpers for importing Claude Code credentials."""

from __future__ import annotations

import json
import logging
import os

from aigateway.core.credential_store import CredentialStore, get_credential_store
from aigateway.core.errors import BootstrapError
from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileState,
    credential_name_for,
    profile_id_for,
)

from .auth import keychain_service_for

logger = logging.getLogger(__name__)

CLAUDE_CODE_SERVICE = "Claude Code-credentials"


async def bootstrap_from_claude_code(
    account_id: str,
    credential_store: CredentialStore | None = None,
    index_store: ProfileIndexStore | None = None,
    cc_account: str | None = None,
) -> None:
    store = credential_store or get_credential_store()
    idx = index_store or ProfileIndexStore(credential_store=store)
    account = cc_account if cc_account is not None else os.environ.get("USER", "")

    existing = await idx.list(account_id)
    if existing:
        logger.debug("bootstrap: account index already populated; skipping")
        return

    cc_raw = store.read(CLAUDE_CODE_SERVICE, account)
    if cc_raw is None:
        logger.info("bootstrap: no Claude Code keychain entry found; nothing to import")
        return

    try:
        outer = json.loads(cc_raw)
        cc_creds = outer["claudeAiOauth"]
        converted = {
            "access_token": cc_creds["accessToken"],
            "refresh_token": cc_creds["refreshToken"],
            "expires_at_ms": int(cc_creds["expiresAt"]),
            "token_type": "Bearer",
        }
    except (KeyError, ValueError, TypeError) as exc:
        raise BootstrapError(f"Claude Code keychain entry has unexpected shape: {exc}") from exc

    store.write(
        keychain_service_for(credential_name_for(account_id, "default")),
        "default",
        json.dumps(converted),
    )
    profile = Profile(
        id=profile_id_for(account_id, "anthropic", "default"),
        account_id=account_id,
        provider="anthropic",
        name="default",
        scopes=cc_creds.get("scopes", []),
        state=ProfileState.AUTHENTICATED,
        defaults=ProfileDefaults(),
    )
    await idx.upsert(profile)
    logger.info("bootstrap: imported Claude Code creds into account-scoped anthropic:default")
