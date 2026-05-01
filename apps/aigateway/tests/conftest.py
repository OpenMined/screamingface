from __future__ import annotations

import pytest

from aigateway.core.credential_store import CredentialStore


class FakeKeychain(CredentialStore):
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def read(self, service: str, account: str) -> str | None:
        return self._data.get((service, account))

    def write(self, service: str, account: str, value: str) -> None:
        self._data[(service, account)] = value

    def delete(self, service: str, account: str) -> None:
        self._data.pop((service, account), None)


@pytest.fixture
def fake_keychain() -> FakeKeychain:
    return FakeKeychain()
