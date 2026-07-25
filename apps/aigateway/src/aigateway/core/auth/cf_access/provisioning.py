"""Just-in-time account provisioning from a verified Cloudflare identity.

STORY: as a user my organisation admitted through Cloudflare Access, I call the
gateway and it works — I never registered and never called /v1/auth/login.
"""

from __future__ import annotations

import logging

from tortoise.exceptions import IntegrityError

from ..models import Account
from .identity import CF_ACCESS_IDP, CfAccessIdentity

logger = logging.getLogger(__name__)


async def get_or_create_cf_access_account(
    identity: CfAccessIdentity,
    *,
    admin_emails: frozenset[str] = frozenset(),
) -> Account | None:
    """Return the account for ``identity``, creating it on first sight.

    Returns ``None`` when the account exists but is deactivated — a gateway
    admin's deactivation must outrank Cloudflare still admitting the user.
    """
    account = await Account.get_or_none(
        external_idp=CF_ACCESS_IDP,
        external_subject=identity.subject,
    )
    if account is None:
        account = await _create(identity, admin_emails=admin_emails)
    elif identity.email and account.email != identity.email:
        # The subject is the identity; email is a mutable label that follows it.
        account.email = identity.email
        await account.save(update_fields=["email"])

    if not account.is_active:
        logger.info("cf_access login refused for deactivated account subject=%s", identity.subject)
        return None
    return account


async def _create(
    identity: CfAccessIdentity,
    *,
    admin_emails: frozenset[str],
) -> Account:
    # INVARIANT: is_admin is granted ONLY from the gateway's own allowlist.
    # Cloudflare policy decides who can reach the gateway; it never decides who
    # holds authority inside it.
    is_admin = bool(identity.email) and identity.email.lower() in admin_emails

    try:
        account = await Account.create(
            username=identity.username,
            password_hash=None,
            display_name=identity.email,
            email=identity.email,
            external_idp=CF_ACCESS_IDP,
            external_subject=identity.subject,
            is_admin=is_admin,
        )
    except IntegrityError:
        # WHY this is the NORMAL path, not an edge case: an SDK with a connection
        # pool issues several first requests at once, so two coroutines routinely
        # race here. The (external_idp, external_subject) unique constraint from
        # OME-590 is what makes the loser's re-read correct rather than a second
        # duplicate account.
        account = await Account.get_or_none(
            external_idp=CF_ACCESS_IDP,
            external_subject=identity.subject,
        )
        if account is None:
            # The constraint that fired was something else — a username collision
            # with a pre-existing local account. Surface it rather than guessing.
            raise
        return account

    logger.info(
        "cf_access provisioned account subject=%s service_token=%s admin=%s",
        identity.subject,
        identity.is_service_token,
        is_admin,
    )
    return account
