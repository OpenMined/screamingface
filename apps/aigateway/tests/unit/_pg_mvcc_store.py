"""Test-support double: a credential/index store modelling PostgreSQL READ COMMITTED.

WHY: the gateway unit harness is SQLite-only and serializes whole transactions on one
connection, so it cannot exhibit the per-row interleaving that OME-307 Blocker 3 needs. This
double models the specific PostgreSQL behaviours that make the delete-wins race real:

- MVCC snapshot visibility — another transaction's uncommitted INSERT is INVISIBLE, so a
  concurrent DELETE of that key finds nothing.
- Missing-row DELETE takes NO lock (there is no row to lock), so it cannot serialize a
  concurrent INSERT of the same key.
- INSERT / UPDATE / index-mutate take that key's row lock, held until COMMIT (a waiter blocks).
- COMMIT publishes the transaction's own writes then releases its locks; ROLLBACK discards
  them.

INVARIANT: because a missing-row DELETE takes no lock, two transactions can only be serialized
by a row that is ALWAYS PRESENT (the account index row / the connection row). A production
ordering that locks the credential row FIRST cannot serialize when that row is absent — which
is exactly the orphan/resurrection this double exposes.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
from collections import defaultdict
from collections.abc import AsyncIterator, Callable

# Per-task transaction scratch (task-local under asyncio, mirroring one pooled connection per
# task pinned by in_transaction()): the pending write-set and the row locks held until COMMIT.
_txn: contextvars.ContextVar[dict | None] = contextvars.ContextVar("_mvcc_txn", default=None)

_DELETED = object()  # tombstone in a transaction's pending write-set


class MvccRowStore:
    """Credential/index store double: PostgreSQL READ COMMITTED row locking + MVCC + rollback."""

    def __init__(self) -> None:
        self.committed: dict[tuple[str, str], str] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = defaultdict(asyncio.Lock)

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        txn: dict = {"pending": {}, "held": []}
        token = _txn.set(txn)
        try:
            yield
        except BaseException:
            raise  # ROLLBACK: pending write-set discarded; locks released in finally.
        else:
            # COMMIT: publish this txn's writes, THEN release locks so a waiter that acquires
            # the lock next observes the committed value (as a real backend would).
            for key, value in txn["pending"].items():
                if value is _DELETED:
                    self.committed.pop(key, None)
                else:
                    self.committed[key] = value
        finally:
            _txn.reset(token)
            for lock in txn["held"]:
                lock.release()

    def _visible(self, txn: dict | None, key: tuple[str, str]) -> str | None:
        # READ COMMITTED: the transaction sees its own pending writes over the committed base.
        if txn is not None and key in txn["pending"]:
            value = txn["pending"][key]
            return None if value is _DELETED else value
        return self.committed.get(key)

    async def _acquire(self, txn: dict | None, key: tuple[str, str]) -> asyncio.Lock | None:
        lock = self._locks[key]
        if txn is None:
            await lock.acquire()  # autocommit statement: caller releases at statement end
            return lock
        if lock not in txn["held"]:
            await lock.acquire()
            txn["held"].append(lock)  # inside a txn: held until COMMIT
        return None

    async def read(self, service: str, account: str) -> str | None:
        await asyncio.sleep(0)
        return self._visible(_txn.get(), (service, account))

    async def write(self, service: str, account: str, value: str) -> None:
        # INSERT (absent) or UPDATE (present): both take the key's row lock.
        key = (service, account)
        txn = _txn.get()
        autolock = await self._acquire(txn, key)
        await asyncio.sleep(0)
        if txn is None:
            self.committed[key] = value
            autolock.release()  # type: ignore[union-attr]
        else:
            txn["pending"][key] = value

    async def delete(self, service: str, account: str) -> None:
        key = (service, account)
        txn = _txn.get()
        await asyncio.sleep(0)
        # INVARIANT: a DELETE of a row not visible to this snapshot takes NO lock and no-ops —
        # this is the missing-row DELETE at the heart of Blocker 3.
        if self._visible(txn, key) is None:
            return
        autolock = await self._acquire(txn, key)
        await asyncio.sleep(0)
        if self._visible(txn, key) is None:  # EvalPlanQual: a just-committed delete wins.
            if autolock is not None:
                autolock.release()
            return
        if txn is None:
            self.committed.pop(key, None)
            autolock.release()  # type: ignore[union-attr]
        else:
            txn["pending"][key] = _DELETED

    async def mutate(
        self, service: str, account: str, mutator: Callable[[str | None], str | None]
    ) -> None:
        # UPDATE of an always-present row with a read-modify-write mutator (the index-row CAS).
        key = (service, account)
        txn = _txn.get()
        autolock = await self._acquire(txn, key)
        try:
            await asyncio.sleep(0)  # yield between SELECT and UPDATE as real I/O would
            next_value = mutator(self._visible(txn, key))  # mutator may raise (conflict)
            if txn is None:
                if next_value is None:
                    self.committed.pop(key, None)
                else:
                    self.committed[key] = next_value
            else:
                txn["pending"][key] = _DELETED if next_value is None else next_value
        finally:
            if txn is None and autolock is not None:
                autolock.release()
