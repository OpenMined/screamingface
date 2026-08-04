from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from tortoise.exceptions import BaseORMException, IntegrityError
from tortoise.expressions import F
from tortoise.transactions import in_transaction

from ..secrets import get_active_secret_store
from ..secrets.mixin import SecretStoreError, SecretStoreMixin
from .global_keys import KEY_VERSION_V2
from .models import RequestCacheEntry

logger = logging.getLogger(__name__)

# INVARIANT: every global v2 row is written with these in place of the origin caller's identity.
# The row is shared, so recording who filled it would both leak an association and make the row
# look scoped when it is not.
GLOBAL_SENTINEL = "global"

# Infrastructure failures that must degrade the cache rather than fail the request. OSError covers
# the socket/file layer under the driver, which does not always arrive wrapped as an ORM error.
_INFRASTRUCTURE_ERRORS = (BaseORMException, OSError)

# A stored payload that will not turn back into a JSON object. ``JSONDecodeError``,
# ``binascii.Error`` and ``UnicodeDecodeError`` are all ``ValueError`` subclasses.
_UNDECODABLE_ERRORS = (SecretStoreError, ValueError, TypeError)


class CacheUnavailable(RuntimeError):
    pass


class CacheAvailability(Protocol):
    def cache_available(self) -> bool: ...


class ConfiguredCacheAvailability:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def cache_available(self) -> bool:
        return self._enabled


class _AlwaysAvailable:
    """Default for unit fixtures that construct the store without a gate."""

    def cache_available(self) -> bool:
        return True


_UNGATED = _AlwaysAvailable()


@dataclass(frozen=True)
class RequestCacheWrite:
    key_hash: str
    key_version: str
    account_id: str
    profile_name: str
    prompt_hash: str
    provider: str
    model: str
    response: dict[str, Any]
    response_size_bytes: int
    expires_at: datetime


@dataclass(frozen=True)
class GlobalRequestCacheWrite:
    """A global v2 fill.

    INVARIANT: closed on purpose. No ``expires_at`` (v2 always persists NULL), no account, profile
    or credential identity, and no prompt text — what the DTO cannot express cannot be persisted.
    """

    key_hash: str
    key_version: str
    prompt_hash: str
    provider: str
    model: str
    response: dict[str, Any]
    response_size_bytes: int


class RequestCacheStore(Protocol):
    async def get(
        self, key_hash: str, *, max_age_seconds: int | None = None
    ) -> dict[str, Any] | None: ...

    async def set(self, entry: RequestCacheWrite) -> None: ...

    async def delete_expired(self) -> int: ...


class GlobalRequestCacheStore(Protocol):
    """The port the chat route consumes for the global lane (OME-305 frozen contract)."""

    async def get_global(self, key_hash: str) -> dict[str, Any] | None: ...

    async def set_if_absent(
        self, entry: GlobalRequestCacheWrite
    ) -> Literal["stored", "race_lost", "not_stored"]: ...

    def cache_available(self) -> bool: ...


async def record_global_hit_metadata(entry_id: uuid.UUID, when: datetime) -> None:
    await RequestCacheEntry.filter(id=entry_id).update(
        hit_count=F("hit_count") + 1, last_hit_at=when
    )


class TortoiseRequestCacheStore:
    """Tortoise-backed implementation of both cache ports (v1 and global v2)."""

    def __init__(
        self,
        secret_store: SecretStoreMixin | None = None,
        availability: CacheAvailability | None = None,
    ) -> None:
        # Lazy by default: the process-wide active store is installed by the
        # app lifespan. Tests may inject one directly.
        self._secret_store = secret_store
        self._availability: CacheAvailability = (
            availability if availability is not None else _UNGATED
        )

    def _secrets(self) -> SecretStoreMixin:
        return self._secret_store if self._secret_store is not None else get_active_secret_store()

    def cache_available(self) -> bool:
        return self._availability.cache_available()

    # --- v1 lane: account/profile scoped, TTL-bound, last-write-wins -----------------------------
    # INVARIANT (OME-305): v1 behaviour is FROZEN. The availability gate and the global lane's
    # never-delete policy apply to the v2 methods only. v1 rows are legacy — readable, unreachable
    # from v2 (§8 #17) — and changing how they are purged or gated is out of this ticket's scope.
    # The only OME-305 edit here is the NULL-safe expiry comparison, which removes a TypeError path.

    async def get(
        self, key_hash: str, *, max_age_seconds: int | None = None
    ) -> dict[str, Any] | None:
        row = await RequestCacheEntry.get_or_none(key_hash=key_hash)
        if row is None:
            return None

        now = datetime.now(UTC)
        # INVARIANT (OME-305): NULL expiry means "never expires". Comparing it would raise.
        if row.expires_at is not None and row.expires_at <= now:
            return None
        if max_age_seconds is not None and row.created_at < now - timedelta(
            seconds=max_age_seconds
        ):
            return None

        try:
            plaintext = await self._secrets().decrypt(row.response_ciphertext)
            response = json.loads(plaintext)
            if not isinstance(response, dict):
                raise ValueError("cached payload is not a JSON object")
        except _UNDECODABLE_ERRORS:
            # Corrupt or undecryptable entry: drop it so it cannot keep
            # short-circuiting dispatch. Log by hash prefix only.
            # AIDEV-NOTE: v1 deletes unconditionally and that is correct HERE — a v1 row is scoped
            # to one account/profile and bounded by a TTL, so dropping it costs one caller one miss.
            logger.warning("request cache entry %s… is corrupt; deleting", key_hash[:12])
            await row.delete()
            return None

        row.hit_count += 1
        row.last_hit_at = now
        await row.save(update_fields=["hit_count", "last_hit_at"])
        return response

    async def set(self, entry: RequestCacheWrite) -> None:
        payload = json.dumps(entry.response, separators=(",", ":"), ensure_ascii=False)
        ciphertext = await self._secrets().encrypt(payload)
        values = {
            "key_version": entry.key_version,
            "account_id": entry.account_id,
            "profile_name": entry.profile_name,
            "prompt_hash": entry.prompt_hash,
            "provider": entry.provider,
            "model": entry.model,
            "response_ciphertext": ciphertext,
            "response_size_bytes": entry.response_size_bytes,
            "expires_at": entry.expires_at,
        }

        row = await RequestCacheEntry.get_or_none(key_hash=entry.key_hash)
        if row is None:
            try:
                await RequestCacheEntry.create(key_hash=entry.key_hash, **values)
                # SF-335: per-write opportunistic purge is INTENTIONAL, not a
                # correctness mechanism. get() refuses expired rows on read
                # (store.py:67-69), so a stale row is never served even if this
                # never runs; it only reclaims space, and the delete is
                # index-assisted (expires_at indexed). If this write path is ever
                # measured as hot, switch to probabilistic GC (SF-335 follow-up);
                # do not add a background task.
                await self.delete_expired()
                return
            except IntegrityError:
                # Lost a concurrent-create race: fall through to update.
                row = await RequestCacheEntry.get(key_hash=entry.key_hash)

        for field, value in values.items():
            setattr(row, field, value)
        await row.save(update_fields=list(values.keys()))
        await self.delete_expired()  # SF-335: intentional opportunistic purge (see note above)

    async def delete_expired(self) -> int:
        # SF-335: index-assisted (expires_at index, request_cache_entry.py:27),
        # NOT a full-table scan. Called opportunistically from set(); see the
        # note there on why this per-write purge is intentional.
        # INVARIANT (OME-305): global rows hold NULL, and `NULL <= now` is NULL in SQL, so this
        # purge can never reach them. Indefinite means indefinite.
        return await RequestCacheEntry.filter(expires_at__lte=datetime.now(UTC)).delete()

    # --- global v2 lane --------------------------------------------------------------------------

    async def get_global(self, key_hash: str) -> dict[str, Any] | None:
        """Look up one global row. ``None`` is a genuine miss; every failure raises.

        INVARIANT: ``None`` means "no such row" and nothing else.
        """
        if not self._availability.cache_available():
            # WHY raise rather than return None: `None` is this module's documented miss signal, and
            # a miss makes the route dispatch AND store. A degraded worker must not write.
            raise CacheUnavailable("this worker is not serving the global cache")

        try:
            row = await RequestCacheEntry.filter(
                key_hash=key_hash,
                # INVARIANT (§8 #17): the version predicate makes v1-unreachability structural
                # rather than a bet on SHA-256 disjointness. It is free — the unique `key_hash`
                # index still drives the lookup. Never discriminate on `expires_at IS NULL`
                # instead: that breaks the moment the deferred configurable-TTL feature lands.
                key_version=KEY_VERSION_V2,
                account_id=GLOBAL_SENTINEL,
                profile_name=GLOBAL_SENTINEL,
            ).first()
        except _INFRASTRUCTURE_ERRORS as exc:
            logger.warning("global cache read failed (%s); bypassing", type(exc).__name__)
            raise CacheUnavailable("global cache read failed") from exc

        if row is None:
            return None
        # A global row is written with NULL. A non-NULL expiry here is not ours: refuse to serve it
        # once it is past, but never rewrite or delete another writer's row on a read.
        if row.expires_at is not None and row.expires_at <= datetime.now(UTC):
            return None

        def reject_non_finite(value: str) -> None:
            raise ValueError(f"non-finite JSON constant: {value}")

        def parse_finite_float(value: str) -> float:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError(f"non-finite JSON number: {value}")
            return parsed

        try:
            response = json.loads(
                row.response_ciphertext,
                parse_constant=reject_non_finite,
                parse_float=parse_finite_float,
            )
            if not isinstance(response, dict):
                raise ValueError("cached payload is not a JSON object")
        except (ValueError, TypeError) as exc:
            logger.warning(
                "global cache entry %s… could not be decoded (%s); refusing to serve it and "
                "leaving the row untouched",
                key_hash[:12],
                type(exc).__name__,
            )
            raise CacheUnavailable("global cache entry could not be decoded") from exc

        try:
            await record_global_hit_metadata(row.id, datetime.now(UTC))
        except _INFRASTRUCTURE_ERRORS as exc:
            logger.warning(
                "global cache hit metadata was not recorded (%s); serving the hit anyway",
                type(exc).__name__,
            )
        return response

    async def set_if_absent(
        self, entry: GlobalRequestCacheWrite
    ) -> Literal["stored", "race_lost", "not_stored"]:
        """Create-only fill: ``stored`` won, ``race_lost`` someone else won, ``not_stored`` failed.

        INVARIANT (plan §5.3): first successful insert wins, permanently. Unlike the v1 ``set``, a
        conflict is NEVER resolved by overwriting — the stored winner is what every later caller has
        already been served, and replacing it would make an identical request answer differently.
        """
        if not self._availability.cache_available():
            return "not_stored"

        try:
            payload = json.dumps(
                entry.response,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "global cache fill could not be serialized (%s); not stored", type(exc).__name__
            )
            return "not_stored"

        try:
            # WHY the explicit transaction: on Postgres a unique-violation aborts the whole
            # transaction it happens in. Nested inside a caller's transaction this becomes a
            # SAVEPOINT, so losing the race rolls back only this INSERT and leaves the caller's
            # transaction usable. The exception must escape the block for that rollback to run.
            #
            # AIDEV-NOTE: the most dangerous edit to this function looks like a tidy-up. Moving the
            # `except` clauses INSIDE this block leaves the aborted transaction in place, and the
            # next statement fails with "current transaction is aborted, commands ignored until end
            # of transaction block" — which then poisons the CALLER's transaction too. Extracting
            # the INSERT into a helper called from in here is fine; wrapping that helper in its own
            # try/except is not.
            async with in_transaction():
                await RequestCacheEntry.create(
                    key_hash=entry.key_hash,
                    key_version=entry.key_version,
                    account_id=GLOBAL_SENTINEL,
                    profile_name=GLOBAL_SENTINEL,
                    prompt_hash=entry.prompt_hash,
                    provider=entry.provider,
                    model=entry.model,
                    response_ciphertext=payload,
                    response_size_bytes=entry.response_size_bytes,
                    expires_at=None,
                )
        except IntegrityError:
            # INVARIANT: `race_lost` means the winner's row is in the table. `IntegrityError` also
            # covers NOT NULL, so the conflict must be CONFIRMED before it is reported as a lost
            # race — a deployment that never applied migration 0009 still has `expires_at NOT NULL`
            # and would otherwise report a lost race, forever, against an empty table.
            #
            # WHY the read is out here and not inside the `async with`: the failed INSERT already
            # aborted that transaction on Postgres, so any statement inside it would raise
            # TransactionManagementError. By now the block has exited and the savepoint is rolled
            # back, so this runs on a usable session.
            return await self._classify_fill_conflict(entry)
        except _INFRASTRUCTURE_ERRORS as exc:
            # AIDEV-NOTE: this clause must stay BELOW `except IntegrityError`. The MRO is
            # IntegrityError -> OperationalError -> BaseORMException, so reordering them makes this
            # one swallow every lost race and silently report `not_stored` instead.
            logger.warning(
                "global cache fill was not persisted (%s); serving the response anyway",
                type(exc).__name__,
            )
            return "not_stored"
        return "stored"

    async def _classify_fill_conflict(
        self, entry: GlobalRequestCacheWrite
    ) -> Literal["race_lost", "not_stored"]:
        """Did a rival fill win this key, or did the row violate some other constraint?"""
        try:
            winner_exists = await RequestCacheEntry.filter(
                key_hash=entry.key_hash,
                key_version=entry.key_version,
                account_id=GLOBAL_SENTINEL,
                profile_name=GLOBAL_SENTINEL,
            ).exists()
        except _INFRASTRUCTURE_ERRORS as exc:
            logger.warning(
                "global cache fill conflict for %s… could not be classified (%s); not stored",
                entry.key_hash[:12],
                type(exc).__name__,
            )
            return "not_stored"

        if not winner_exists:
            # Loud on purpose: nothing is in the table, so no amount of traffic will fill it.
            logger.warning(
                "global cache fill %s… was rejected by a constraint other than the entry key and "
                "no row is stored; is the database schema up to date (migration 0009)?",
                entry.key_hash[:12],
            )
            return "not_stored"

        logger.debug(
            "global cache fill %s… lost the race; keeping the stored winner",
            entry.key_hash[:12],
        )
        return "race_lost"
