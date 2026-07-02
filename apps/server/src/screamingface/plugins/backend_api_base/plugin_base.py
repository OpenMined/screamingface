"""Shared :class:`BackendApiPluginBase` for direct-API backend plugins.

Every ``*_backend_api`` plugin (claude, codex, gemini, ollama) ran
~150-200 lines of nearly-identical bookkeeping: profile name validation,
schema customization, the standard ``setup`` body, and a
``handle_backend_call`` shim that just wires the interpreter. Real
differences are: plugin metadata, settings env_prefix + a couple of
provider-specific fields, the URL-prefix string, the router factory,
and the interpreter class.

This base concentrates the shared behavior. Each subclass shrinks to
~30-40 lines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from screamingface.core.backend_paths import PROFILE_ALIAS_RE, is_valid_profile_alias
from screamingface.core.local_only import assert_loopback_server_bind
from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.backend_api_base.models import BackendProfile

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry
    from screamingface.plugins.llm_base.routes_shared import BackendApiConfig
    from screamingface.plugins.url4_executor.scope import Env

_PROFILE_NAME_RE = PROFILE_ALIAS_RE


class BackendApiSettingsBase(PluginSettings):
    """Settings shared by every direct-API backend plugin.

    Subclasses override ``model_config.env_prefix`` and may add
    provider-specific fields (e.g. ``base_url`` for ollama,
    ``fallback_models`` for gemini).

    CLI-only settings (``permission_mode``, ``dangerously_skip_permissions``,
    ``max_budget_usd``) are accepted for ``sf.json`` compatibility but
    silently ignored at request time. The ``/run`` route rejects them
    explicitly via SF-115.
    """

    model_config = SettingsConfigDict(
        env_prefix="SF_BACKEND_API__",
        env_nested_delimiter="__",
    )

    default_model: str | None = Field(
        default=None,
        description="Default model. Provider-specific fallback applies if unset.",
    )
    default_effort: str = Field(
        default="medium",
        description="Default effort level.",
    )
    interpreter_system_prompt: str = Field(
        default=(
            "You are a helpful assistant. Answer the user's question based only on "
            "the provided context. Be concise and factual."
        ),
        description="System prompt used by the url4 interpreter endpoint.",
    )
    timeout_seconds: float = Field(
        default=300.0,
        description="Default request timeout in seconds (httpx read timeout).",
    )
    max_budget_usd: float | None = Field(
        default=None,
        description=(
            "CLI-only budget cap. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend."
        ),
    )
    permission_mode: str | None = Field(
        default=None,
        description=(
            "CLI-only setting. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend."
        ),
    )
    dangerously_skip_permissions: bool = Field(
        default=False,
        description=(
            "CLI-only setting. Accepted for sf.json compatibility but "
            "silently ignored by the direct-API backend."
        ),
    )
    profiles: dict[str, BackendProfile] = Field(
        default_factory=dict,
        description="Named pre-configured execution profiles.",
    )
    default_profile: str | None = Field(
        default=None,
        description="Profile to use when none is specified. Must exist in profiles when set.",
    )

    @field_validator("profiles")
    @classmethod
    def _validate_profile_keys(cls, v: dict[str, BackendProfile]) -> dict[str, BackendProfile]:
        for key in v:
            if not _PROFILE_NAME_RE.match(key):
                msg = (
                    f"Invalid profile name {key!r}: must be lowercase "
                    "alphanumeric, hyphens, or underscores, starting with "
                    "a letter or digit."
                )
                raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _validate_default_profile(self) -> BackendApiSettingsBase:
        if self.default_profile and self.profiles and self.default_profile not in self.profiles:
            msg = (
                f"default_profile {self.default_profile!r} not found in profiles. "
                f"Available: {list(self.profiles.keys())}"
            )
            raise ValueError(msg)
        return self


class BackendApiPluginBase(Plugin):
    """Shared lifecycle for direct-API backend plugins.

    Subclasses must declare:

    - The standard :class:`Plugin` class attrs (``name``, ``description``,
      ``tags``, ``depends``, ``conflicts``, ``backend_call_paths``,
      ``settings_class``).
    - ``schema_link_base``: URL prefix shown to RJSF as the "x-link-base"
      hint on the ``profiles`` field, e.g. ``"/claude/"``.
    - ``create_route_bundle``: a callable returning the provider's generated
      APIRouter plus the BackendApiConfig that powers shared profile helpers.
    - ``create_router``: compatibility callable returning only the provider's
      APIRouter. Signature ``(settings, app)`` matches the existing factories.
    - ``_make_interpreter(app)``: lazy interpreter construction. Each
      subclass imports its provider-specific Interpreter class inside
      this method to keep module-load free of circular imports.
    """

    schema_link_base: ClassVar[str] = "/"
    create_route_bundle: ClassVar[Callable[..., Any]]
    create_router: ClassVar[Callable[..., Any]]
    # SF-290: LLM backends pack context into a prompt, so the url4 dispatcher
    # pre-fetches any ``/...`` / ``http(s)://`` ref in a backend call's context
    # before handing it over. Backends that consume a raw locator instead
    # (e.g. python_runner, which fetches its own script) leave this False.
    resolves_context_sources: ClassVar[bool] = True
    # SF-346: this plugin can resolve a URL4 backend-call suffix
    # (``/<path>/<alias>``) to one of its configured ``settings.profiles`` and
    # execute it. The URL4 dispatcher reads this flag by duck-typing (getattr) and
    # MUST NOT import this class, so python-runner and other non-profile plugins
    # simply never opt in and ``/python/foo`` stays an unknown backend call.
    supports_profile_aliases: ClassVar[bool] = True
    # Shared execution wiring captured explicitly at setup() so alias dispatch
    # runs profiles through the same helpers as the HTTP profile route.
    _api_config: BackendApiConfig | None = None

    def customize_schema(self, schema: dict) -> dict:
        settings: BackendApiSettingsBase = self.settings  # type: ignore[assignment]
        profile_names = list(settings.profiles.keys())
        props = schema.get("properties", {})
        if profile_names and "default_profile" in props:
            props["default_profile"]["enum"] = profile_names
        if "profiles" in props:
            props["profiles"]["x-link-base"] = self.schema_link_base
        return schema

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,  # noqa: ARG002 — required by Plugin contract
        classes: ClassRegistry,  # noqa: ARG002 — required by Plugin contract
        routes: RouteRegistry,
    ) -> None:
        self._assert_loopback_server_bind(app)
        bundle = type(self).create_route_bundle(self.settings, app)
        routes.add_router(self.name, bundle.router, prefix="")
        # SF-346: capture the shared BackendApiConfig explicitly, so
        # handle_backend_alias can execute profiles through the same helpers the
        # HTTP profile route uses (no divergent second execution path).
        self._api_config = bundle.config

    def _assert_loopback_server_bind(self, app: FastAPI) -> None:
        assert_loopback_server_bind(
            app,
            self.name,
            allow_env_vars=("SF_SERVER_ALLOW_LAN",),
        )

    async def handle_backend_call(
        self,
        intent: str,
        *,
        sources: str = "",
        app: FastAPI,
        env: Env | None = None,
    ) -> str:
        """Dispatch a url4 backend-call to the provider.

        Constructs a per-plugin Interpreter via :meth:`_make_interpreter`
        and delegates to its ``process(sources, intent)`` method — the
        same path the ``GET /<prefix>?q=`` route uses.
        """
        del env
        interpreter = self._make_interpreter(app)
        return await interpreter.process(sources=sources, intent=intent)

    async def handle_backend_alias(
        self,
        alias: str,
        *,
        sources: str = "",
        intent: str = "",
        app: FastAPI,  # noqa: ARG002 — signature parity with handle_backend_call
        env: Env | None = None,
    ) -> str:
        """Execute a URL4 profile alias (``/<backend>/<alias>(ctx)!intent``).

        Called by the URL4 dispatcher only for plugins that advertise
        :attr:`supports_profile_aliases`. Validates the alias with the same
        ``_PROFILE_NAME_RE`` that guards profile-config keys — one regex, so the
        alias gate and the config-key rule can never drift — then runs the
        matching profile through the shared backend-profile helper so the
        profile's model reaches the backend. Raises with a clear URL4-facing
        message on an invalid or unknown alias.
        """
        del env
        profile = self.resolve_backend_alias_profile(alias, app=app)
        return await self.handle_resolved_backend_alias(
            profile,
            sources=sources,
            intent=intent,
            app=app,
        )

    async def handle_resolved_backend_alias(
        self,
        profile: BackendProfile,
        *,
        sources: str = "",
        intent: str = "",
        app: FastAPI,
        env: Env | None = None,
    ) -> str:
        """Execute a URL4 profile alias after the dispatcher resolved it once."""

        del env
        if self._api_config is None:
            raise RuntimeError(
                f"{self.name!r} cannot dispatch resolved profile alias: backend-api "
                "config was not captured during setup()."
            )
        self._refresh_api_config_for_alias(app)
        # Local import — llm_base imports backend_api_base.models, so a module-load
        # import here would cycle. Mirrors the lazy-import pattern in routes_shared.
        from screamingface.plugins.llm_base.routes_shared import execute_backend_profile_text

        return await execute_backend_profile_text(
            self._api_config, profile, packed_context=sources, intent=intent
        )

    def backend_alias_profiles(self) -> dict[str, BackendProfile]:
        """Profiles to advertise as URL4 aliases in `/plugins/backend-aliases`."""

        profiles = getattr(self.settings, "profiles", {}) or {}
        if not isinstance(profiles, dict):
            return {}
        default_profile = getattr(self.settings, "default_profile", None)
        return {
            name: profile
            for name, profile in profiles.items()
            if isinstance(name, str) and name and name != default_profile
        }

    def validate_backend_alias(self, alias: str, *, base_path: str | None = None) -> None:
        """Validate alias syntax/existence before any context fetch or backend run."""

        self.resolve_backend_alias_profile(alias, base_path=base_path)

    def resolve_backend_alias_profile(
        self, alias: str, *, base_path: str | None = None, app: FastAPI | None = None
    ) -> BackendProfile:
        """Return the profile object backing a URL4 alias, or raise clearly."""

        base = self._alias_base_path(base_path)
        self._validate_profile_alias(alias, base)
        profile = self._configured_alias_profile(alias)
        if profile is None:
            profile = self._resolve_alias_fallback(alias, base_path=base, app=app)
        if profile is None:
            raise self._unknown_profile_alias(alias, base)
        return profile

    async def resolve_backend_alias_profile_async(
        self, alias: str, *, base_path: str | None = None, app: FastAPI | None = None
    ) -> BackendProfile:
        """Async resolver hook for plugins whose alias fallback does I/O."""

        base = self._alias_base_path(base_path)
        self._validate_profile_alias(alias, base)
        profile = self._configured_alias_profile(alias)
        if profile is None:
            profile = await self._resolve_alias_fallback_async(alias, base_path=base, app=app)
        if profile is None:
            raise self._unknown_profile_alias(alias, base)
        return profile

    def _alias_base_path(self, base_path: str | None) -> str:
        return base_path or (self.backend_call_paths[0] if self.backend_call_paths else "")

    def _validate_profile_alias(self, alias: str, base: str) -> None:
        if not is_valid_profile_alias(alias):
            raise ValueError(
                f"Invalid profile alias {alias!r} for backend {base}. "
                f"Aliases must match {_PROFILE_NAME_RE.pattern}."
            )

    def _configured_alias_profile(self, alias: str) -> BackendProfile | None:
        profiles = getattr(self.settings, "profiles", {}) or {}
        return profiles.get(alias) if isinstance(profiles, dict) else None

    def _resolve_alias_fallback(
        self, alias: str, *, base_path: str, app: FastAPI | None = None
    ) -> BackendProfile | None:
        """Subclass hook for non-configured aliases."""

        del alias, base_path, app
        return None

    async def _resolve_alias_fallback_async(
        self, alias: str, *, base_path: str, app: FastAPI | None = None
    ) -> BackendProfile | None:
        return self._resolve_alias_fallback(alias, base_path=base_path, app=app)

    def _unknown_profile_alias(self, alias: str, base: str) -> ValueError:
        return ValueError(f"No profile alias {alias!r} is configured for backend {base}.")

    def _refresh_api_config_for_alias(self, app: FastAPI) -> None:
        del app
        if self._api_config is not None:
            self._api_config.settings = self.settings

    def _make_interpreter(self, app: FastAPI) -> Any:
        """Subclass hook: build a fresh provider-specific interpreter.

        Subclasses must implement this; the lazy interpreter import goes
        inside the override to avoid module-load-time circular imports.
        """
        raise NotImplementedError(f"{type(self).__name__} must override _make_interpreter()")


__all__ = ["BackendApiPluginBase", "BackendApiSettingsBase"]
