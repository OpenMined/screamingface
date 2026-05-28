"""Settings for the AIGateway OAuth callback bridge."""

from __future__ import annotations

from ipaddress import ip_address

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from screamingface.plugin import PluginSettings


class AigwCallbackSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_AIGW_CALLBACK__",
        env_nested_delimiter="__",
    )

    enabled: bool = Field(
        default=True,
        description="Enable the external-mode local OAuth callback bridge.",
    )
    ttl_seconds: int = Field(
        default=600,
        ge=1,
        description="Seconds to keep an in-flight OAuth callback state.",
    )
    host: str = Field(
        default="localhost",
        description="Loopback host used in provider redirect_uri values.",
    )
    anthropic_port: int = Field(default=9105, ge=1, le=65535)
    gemini_port: int = Field(default=9105, ge=1, le=65535)
    codex_ports: list[int] = Field(default_factory=lambda: [1455, 1457])

    @field_validator("host")
    @classmethod
    def _host_must_be_loopback(cls, value: str) -> str:
        host = value.strip()
        if host.lower() == "localhost":
            return host
        try:
            if ip_address(host).is_loopback:
                return host
        except ValueError:
            pass
        raise ValueError("host must be localhost or a loopback IP address")

    @field_validator("codex_ports")
    @classmethod
    def _codex_ports_must_be_valid(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("codex_ports must not be empty")
        for port in value:
            if port < 1 or port > 65535:
                raise ValueError("codex_ports values must be between 1 and 65535")
        return value
