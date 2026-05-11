from __future__ import annotations

import inspect

from pydantic import SecretStr

from aigateway.core.auth import provisioning


def test_provisioning_token_uses_compare_digest() -> None:
    source = inspect.getsource(provisioning.verify_provisioning_token)
    assert "hmac.compare_digest" in source
    assert "token ==" not in source
    assert "== token" not in source
    assert provisioning.verify_provisioning_token("x" * 32, SecretStr("x" * 32))
    assert not provisioning.verify_provisioning_token("x" * 31 + "y", SecretStr("x" * 32))
