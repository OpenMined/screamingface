from __future__ import annotations

import hmac

from pydantic import SecretStr

PROVISIONING_HEADER = "X-Aigw-Provisioning-Token"


def verify_provisioning_token(candidate: str | None, expected: SecretStr) -> bool:
    if candidate is None:
        return False
    return hmac.compare_digest(candidate, expected.get_secret_value())
