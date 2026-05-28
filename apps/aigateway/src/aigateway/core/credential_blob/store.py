from __future__ import annotations

from typing import Protocol

from tortoise.exceptions import DoesNotExist, IntegrityError

from .model import CredentialBlob


class CredentialBlobStore(Protocol):
    async def read(self, service: str, account: str) -> str | None: ...

    async def write(self, service: str, account: str, value: str) -> None: ...

    async def delete(self, service: str, account: str) -> None: ...


class ORMStore:
    async def read(self, service: str, account: str) -> str | None:
        blob = await CredentialBlob.filter(service=service, account=account).first()
        return blob.value if blob is not None else None

    async def write(self, service: str, account: str, value: str) -> None:
        try:
            blob = await CredentialBlob.get(service=service, account=account)
        except DoesNotExist:
            try:
                await CredentialBlob.create(service=service, account=account, value=value)
                return
            except IntegrityError:
                blob = await CredentialBlob.get(service=service, account=account)
        blob.value = value
        await blob.save(update_fields=["value", "updated_at"])

    async def delete(self, service: str, account: str) -> None:
        await CredentialBlob.filter(service=service, account=account).delete()
