from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any


def unsigned_jwt(claims: dict[str, Any]) -> str:
    def _segment(data: dict[str, Any]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{_segment({'alg': 'none', 'typ': 'JWT'})}.{_segment(claims)}."


def write_codex_auth(
    codex_home: Path,
    *,
    access_exp: float | None = None,
    id_claims: dict[str, Any] | None = None,
    account_id: str = "chatgpt-account-1",
    refresh_token: str = "refresh-token-1",
    openai_api_key: str | None = None,
) -> Path:
    tokens = {
        "access_token": unsigned_jwt(
            {"exp": access_exp if access_exp is not None else time.time() + 3600}
        ),
        "refresh_token": refresh_token,
        "id_token": unsigned_jwt(id_claims or {"sub": "sub-1", "email": "user@example.com"}),
        "account_id": account_id,
    }
    auth_path = codex_home / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": openai_api_key,
                "tokens": tokens,
            }
        )
    )
    auth_path.chmod(0o600)
    return auth_path
