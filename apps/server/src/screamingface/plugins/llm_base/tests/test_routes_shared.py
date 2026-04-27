"""Unit tests for the shared backend-api route helpers.

Specifically covers the SF-115 boundary check that rejects CLI-only
fields explicitly at the ``/run`` route.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from screamingface.plugins.backend_api_base.models import RunRequest
from screamingface.plugins.llm_base.constants import (
    CLI_ONLY_FIELD_DEFAULTS,
    CLI_ONLY_FIELDS,
)
from screamingface.plugins.llm_base.routes_shared import _reject_cli_only_fields


def _default_request(**overrides) -> RunRequest:
    return RunRequest(prompt="hi", **overrides)


def test_default_request_passes() -> None:
    _reject_cli_only_fields(_default_request(), "claude-backend-api")


@pytest.mark.parametrize(
    "field,value",
    [
        ("add_dirs", ["/tmp"]),
        ("mcp_config", "/etc/mcp.json"),
        ("permission_mode", "ask"),
        ("dangerously_skip_permissions", True),
        ("no_session_persistence", False),  # default is True; False is non-default
        ("tools", ["bash"]),
        ("allowed_tools", ["read"]),
        ("disallowed_tools", ["write"]),
    ],
)
def test_each_cli_field_rejected(field: str, value: object) -> None:
    req = _default_request(**{field: value})
    with pytest.raises(HTTPException) as ei:
        _reject_cli_only_fields(req, "claude-backend-api")
    assert ei.value.status_code == 422
    assert field in ei.value.detail
    assert "claude-backend-api" in ei.value.detail


def test_multiple_offending_fields_all_named() -> None:
    req = _default_request(mcp_config="/x", tools=["bash"], permission_mode="ask")
    with pytest.raises(HTTPException) as ei:
        _reject_cli_only_fields(req, "codex-backend-api")
    detail = ei.value.detail
    for f in ("mcp_config", "tools", "permission_mode"):
        assert f in detail


def test_constant_covers_runrequest_defaults() -> None:
    """Defaults map must match the actual RunRequest defaults — guards
    drift if a new CLI-only field is added without updating both."""
    req = _default_request()
    for f in CLI_ONLY_FIELDS:
        assert getattr(req, f) == CLI_ONLY_FIELD_DEFAULTS[f], (
            f"Default mismatch for {f}: model={getattr(req, f)!r} "
            f"vs constant={CLI_ONLY_FIELD_DEFAULTS[f]!r}"
        )
