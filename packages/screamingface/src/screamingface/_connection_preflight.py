"""Fresh provider-connection checks at model-backed stage boundaries."""

from __future__ import annotations

from collections.abc import Sequence

from screamingface import connections
from screamingface._profile import ProviderRecord, Registry
from screamingface._requirements import ConnectionRequirement
from screamingface.errors import ConnectionRequiredError


def require_connections(
    requirements: Sequence[ConnectionRequirement],
    registry: Registry,
) -> None:
    """Raise one structured error before spend when a required provider is unavailable."""

    if not requirements:
        return
    current = {item.provider: item for item in connections._list_for_registry(registry)}
    missing = tuple(
        requirement
        for requirement in requirements
        if current[requirement.provider].status != "connected"
    )
    if not missing:
        return

    providers = _unique(item.provider for item in missing)
    models = _unique(item.model for item in missing if item.model is not None)
    roles = _unique(item.role for item in missing)
    records = {provider.id: provider for provider in registry.providers}
    actions = "; ".join(_action(records[provider]) for provider in providers)
    # INVARIANT: Execution methods report every missing provider together and never open a
    # notebook widget or make a model request as a side effect of preflight.
    raise ConnectionRequiredError(
        f"Connect the required connection(s) before execution: {actions}",
        providers=providers,
        models=models,
        roles=roles,
    )


def _action(provider: ProviderRecord) -> str:
    quoted = repr(provider.id)
    if provider.auth_methods == ("oauth",):
        return f"sf.connect({quoted})"
    if provider.auth_methods == ("api_key",):
        return f"sf.connect({quoted}, api_key=...)"
    return f"sf.connect({quoted}, method='oauth') or sf.connect({quoted}, api_key=...)"


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__ = ["require_connections"]
