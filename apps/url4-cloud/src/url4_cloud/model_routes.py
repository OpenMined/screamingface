"""Shared model-route configuration for the serving and execution halves.

The Engine's executable model world is declared in ``url4.toml``. The control plane reads only
the model ids so discovery can be projected onto that world; the Runner parses the complete
configuration. Keeping id validation here gives both halves one definition of an executable
model route without letting either import the other.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path

from url4_cloud import job_env

_MODEL_ID_RE = re.compile(r"[A-Za-z0-9\-_.~]+(?:/[A-Za-z0-9\-_.~]+)*", re.ASCII)


class ModelRouteConfigError(ValueError):
    """The declared model-route portion of ``url4.toml`` is unusable."""


def require_model_route_id(value: str) -> str:
    """Return one URL4-expression-compatible model id, or fail before startup.

    URL4 expression paths use the narrow ``segment`` production. In particular, ``:`` belongs
    to data paths but not callable expression paths, and percent-encoding does not change that.
    Model ids omit the leading slash because the Runner derives the route as ``"/" + id``.
    """

    if not value:
        raise ModelRouteConfigError("[aigateway] declares an empty model id")
    if value.startswith("/"):
        raise ModelRouteConfigError(
            f"model id {value!r} must not start with '/' — the route path is derived as '/' + id"
        )
    if _MODEL_ID_RE.fullmatch(value) is None:
        raise ModelRouteConfigError(
            f"model id {value!r} is not a valid URL4 expression path — each segment may contain "
            "only ASCII letters, digits, '-', '_', '.', or '~'"
        )
    return value


def declared_model_ids(env: Mapping[str, str]) -> frozenset[str]:
    """Read the Engine's declared model ids from the configured ``url4.toml``.

    This deliberately reads only ``[aigateway].models``. The Runner remains the authority for
    every other setting and validates the complete file when it starts. Both accepted model
    entry spellings are handled here because they describe the same route contract.
    """

    path = Path(env.get(job_env.RUNNER_CONFIG, job_env.DEFAULT_RUNNER_CONFIG_PATH))
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ModelRouteConfigError(
            f"cannot read declared model routes from {str(path)!r}: {exc}"
        ) from exc
    aigateway = raw.get("aigateway")
    if not isinstance(aigateway, Mapping):
        raise ModelRouteConfigError("runner config must contain an [aigateway] table")
    entries = aigateway.get("models")
    if not isinstance(entries, list) or not entries:
        raise ModelRouteConfigError("[aigateway] must declare at least one model")
    ids = tuple(_entry_id(entry) for entry in entries)
    if len(set(ids)) != len(ids):
        raise ModelRouteConfigError("[aigateway] declares duplicate model ids")
    return frozenset(ids)


def _entry_id(entry: object) -> str:
    if isinstance(entry, str):
        return require_model_route_id(entry)
    if isinstance(entry, Mapping):
        value = entry.get("id")
        if not isinstance(value, str):
            raise ModelRouteConfigError("[[aigateway.models]] entry must contain a string `id`")
        return require_model_route_id(value)
    raise ModelRouteConfigError(
        f"[aigateway] model entry must be a table or an id string, got {entry!r}"
    )


__all__ = ["ModelRouteConfigError", "declared_model_ids", "require_model_route_id"]
