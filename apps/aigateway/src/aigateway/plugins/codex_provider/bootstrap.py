from __future__ import annotations

import logging

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileState, profile_id_for

from .auth import CodexOAuth
from .routes import account_label_from_claims

logger = logging.getLogger(__name__)


async def bootstrap_from_codex_cli(*, account_id: str, index_store: ProfileIndexStore) -> None:
    existing = await index_store.get(account_id, "codex", "default")
    if existing is not None:
        return
    strategy = CodexOAuth(profile_name="default")
    try:
        creds = strategy._read_credential()
    except Exception:
        logger.info("bootstrap: no usable Codex CLI auth file found; nothing to import")
        return
    profile = Profile(
        id=profile_id_for(account_id, "codex", "default"),
        account_id=account_id,
        provider="codex",
        name="default",
        account_label=account_label_from_claims(creds.get("id_token")),
        state=ProfileState.AUTHENTICATED,
        defaults=ProfileDefaults(),
    )
    await index_store.upsert(profile)
