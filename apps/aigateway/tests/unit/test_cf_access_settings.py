"""Fail-fast configuration for Cloudflare Access (OME-593).

Every case here is a way the gateway could come up believing it is protected
while actually admitting unauthenticated callers. They are startup errors on
purpose: a misconfiguration that only shows up as a runtime 200 is worse than
one that refuses to boot.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aigateway.config import Settings

_VALID = {
    "AIGATEWAY_CF_ACCESS_ENABLED": "true",
    "AIGATEWAY_CF_ACCESS_TEAM_DOMAIN": "myteam.cloudflareaccess.com",
    "AIGATEWAY_CF_ACCESS_AUD": "a" * 64,
}


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for key in (
        *_VALID,
        "AIGATEWAY_AUTH_ENABLED",
        "AIGATEWAY_CF_ACCESS_ADMIN_EMAILS",
    ):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def _settings(_isolate_env, **env: str) -> Settings:
    for key, value in env.items():
        _isolate_env.setenv(key, value)
    # type: ignore-free: Settings' generated __init__ has no _env_file param in
    # its signature, so configure the source via model_config at call time.
    return Settings()


def test_disabled_by_default(_isolate_env) -> None:
    settings = _settings(_isolate_env)

    assert settings.cf_access_enabled is False
    assert settings.cf_access_team_domain is None


def test_valid_configuration_is_accepted(_isolate_env) -> None:
    settings = _settings(_isolate_env, **_VALID)

    assert settings.cf_access_enabled is True
    assert settings.cf_access_team_domain == "myteam.cloudflareaccess.com"


def test_enabling_cf_access_with_auth_disabled_refuses_to_start(_isolate_env) -> None:
    # INVARIANT: the worst possible combination. auth_enabled=False makes
    # current_account return anonymous_account() for EVERY caller, behind a
    # gateway the operator believes Cloudflare is protecting.
    with pytest.raises(ValidationError, match="AIGATEWAY_AUTH_ENABLED"):
        _settings(_isolate_env, **_VALID, AIGATEWAY_AUTH_ENABLED="false")


@pytest.mark.parametrize("missing", ["AIGATEWAY_CF_ACCESS_TEAM_DOMAIN", "AIGATEWAY_CF_ACCESS_AUD"])
def test_enabling_without_team_domain_or_aud_refuses_to_start(_isolate_env, missing: str) -> None:
    env = {key: value for key, value in _VALID.items() if key != missing}

    with pytest.raises(ValidationError):
        _settings(_isolate_env, **env)


@pytest.mark.parametrize(
    "bad_domain",
    [
        "https://myteam.cloudflareaccess.com",
        "myteam.cloudflareaccess.com/cdn-cgi",
        "attacker.com:8443",
        "user@attacker.com",
        "localhost",
        "myteam.cloudflareaccess.com?x=1",
    ],
)
def test_team_domain_must_be_a_bare_hostname(_isolate_env, bad_domain: str) -> None:
    # INVARIANT: the JWKS URL is built by interpolating this value. Anything that
    # can redirect key retrieval to an attacker-controlled host is a TOTAL auth
    # bypass — the gateway would verify assertions the attacker signed.
    env = {**_VALID, "AIGATEWAY_CF_ACCESS_TEAM_DOMAIN": bad_domain}

    with pytest.raises(ValidationError):
        _settings(_isolate_env, **env)


def test_admin_emails_parse_from_a_comma_separated_list(_isolate_env) -> None:
    settings = _settings(
        _isolate_env,
        **_VALID,
        AIGATEWAY_CF_ACCESS_ADMIN_EMAILS=" Admin@Example.com , second@example.com ",
    )

    assert settings.cf_access_admin_email_set == {"admin@example.com", "second@example.com"}


def test_admin_emails_default_to_empty(_isolate_env) -> None:
    assert _settings(_isolate_env, **_VALID).cf_access_admin_email_set == frozenset()
