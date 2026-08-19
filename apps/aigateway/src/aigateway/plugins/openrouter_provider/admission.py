"""Dynamic OpenRouter model admission — the decision ladder (OME-879).

FEATURE: run any OpenRouter model (OME-878). When a caller asks for an
OpenRouter model outside the seeded list, this module answers "may it join the
served catalog right now?" — think of it as a bouncer with a guest list it
re-reads every few minutes.

The ladder runs cheapest-first, in EXECUTION order:

1. Flag — dynamic admission switched off (`AIGW_OPENROUTER_DYNAMIC=false`)
   refuses everything, before any other work.
2. Provider — a disabled provider (`AIGW_OPENROUTER_ENABLED=false`) can serve
   nothing, so admitting into it would be a lie.
3. Shape — the id must be `openrouter/<author>/<model>` exactly: no `:variant`
   (a second route around gateway-owned search/caching, see `is_online_variant`)
   and no `~` (the engine's colon escape, OME-873 — a `~` id is an encoding,
   not a model).
4. Credential — the calling account must hold a usable OpenRouter credential;
   without one the admitted model could never dispatch, so refuse now with the
   knob's name instead of mid-run later.
5. Catalog — only now spend a network fetch: the model must appear in
   OpenRouter's public catalog (bounded OME-479 transport, TTL-cached in
   app-owned scratch so a burst of admissions costs one dial).

Worked example: `openrouter/qwen/qwen2.5-7b-instruct` with the flag on, the
provider enabled and a stored key walks 1-4 for free, costs one catalog fetch
at 5, and is granted; re-admitting it 10s later hits the cached id set and
costs nothing. `openrouter/qwen/qwen-typo` walks the same ladder and is refused
at 5 with `model_not_on_openrouter` — $0 spent either way.

INVARIANT: refusals are values, never exceptions — the route serves them as a
200 answer, and an outage (`openrouter_catalog_unavailable`) is always distinct
from a typo verdict (`model_not_on_openrouter`).
"""

from __future__ import annotations

import time
from typing import Any

from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryHttpClient,
    DiscoveryLimits,
    fetch_discovery_json,
)
from aigateway.core.plugin_base import ModelAdmission, ModelEntry

from .discovery import ALLOWED_ORIGINS, MODELS_URL, parse_catalog_model_ids
from .settings import (
    GATEWAY_MODEL_PREFIX,
    OpenRouterPluginSettings,
    is_valid_upstream_model_id,
)

# WHY 300s: long enough that a notebook's burst of admissions costs one catalog
# fetch, short enough that a model newly published on OpenRouter is admissible
# within minutes.
CATALOG_TTL_SECONDS = 300.0

_CACHE_IDS_KEY = "ids"
_CACHE_EXPIRES_KEY = "expires_at"


def _admissible_upstream_id(upstream: str) -> bool:
    # Stricter than the D8 grammar on purpose: admission mints catalog entries,
    # so `:variant` and `~` shapes the grammar tolerates elsewhere are refused.
    return is_valid_upstream_model_id(upstream) and ":" not in upstream and "~" not in upstream


async def _catalog_ids(
    *,
    client: DiscoveryHttpClient,
    limits: DiscoveryLimits,
    cache: dict[str, Any],
    now: float,
) -> frozenset[str] | None:
    ids = cache.get(_CACHE_IDS_KEY)
    expires_at = cache.get(_CACHE_EXPIRES_KEY)
    if isinstance(ids, frozenset) and isinstance(expires_at, float) and now < expires_at:
        return ids
    payload = await fetch_discovery_json(
        MODELS_URL, allowed_origins=ALLOWED_ORIGINS, client=client, limits=limits
    )
    parsed = parse_catalog_model_ids(payload)
    if parsed is None:
        return None
    cache[_CACHE_IDS_KEY] = parsed
    cache[_CACHE_EXPIRES_KEY] = now + CATALOG_TTL_SECONDS
    return parsed


async def admit_openrouter_model(
    model_id: str,
    *,
    settings: OpenRouterPluginSettings,
    client: DiscoveryHttpClient | None,
    limits: DiscoveryLimits | None,
    cache: dict[str, Any],
    credentialed: bool,
    now: float | None = None,
) -> ModelAdmission:
    """Walk the module's decision ladder for one gateway model id.

    Args: ``model_id`` is the gateway-form id (`openrouter/...`); ``client``/
    ``limits`` are the bounded discovery transport (``None`` when discovery is
    disabled — stage 5 then refuses as an outage); ``cache`` is app-owned
    scratch for the TTL'd catalog id set; ``credentialed`` is the caller's
    account-scoped credential verdict (resolved by the route); ``now`` is a
    monotonic-clock override for tests. Returns a ``ModelAdmission`` — a grant
    carries the ready-to-serve ``ModelEntry``, a refusal carries code+message.
    """
    # Stage 1 — flag.
    if not settings.dynamic:
        return ModelAdmission.refused(
            "dynamic_admission_disabled",
            "dynamic model admission is switched off on this gateway "
            "(AIGW_OPENROUTER_DYNAMIC=false)",
        )
    # Stage 2 — provider.
    if not settings.enabled:
        return ModelAdmission.refused(
            "provider_disabled",
            "the OpenRouter provider is disabled on this gateway "
            "(set AIGW_OPENROUTER_ENABLED=true)",
        )
    # Stage 3 — shape.
    upstream = (
        model_id[len(GATEWAY_MODEL_PREFIX) :] if model_id.startswith(GATEWAY_MODEL_PREFIX) else None
    )
    if upstream is None or not _admissible_upstream_id(upstream):
        return ModelAdmission.refused(
            "invalid_model_id",
            f"{model_id!r} is not admissible: expected 'openrouter/<author>/<model>' "
            "with no ':variant' and no '~'",
        )
    # Stage 4 — credential.
    if not credentialed:
        return ModelAdmission.refused(
            "provider_not_credentialed",
            "your account holds no usable OpenRouter credential on this gateway — "
            "connect an OpenRouter API key first",
        )
    # Stage 5 — catalog.
    if client is None or limits is None:
        return ModelAdmission.refused(
            "openrouter_catalog_unavailable",
            "the OpenRouter catalog cannot be checked: parameter discovery is "
            "disabled on this gateway (AIGW_DISCOVERY_ENABLED)",
        )
    try:
        catalog_ids = await _catalog_ids(
            client=client,
            limits=limits,
            cache=cache,
            now=now if now is not None else time.monotonic(),
        )
    except DiscoveryError:
        catalog_ids = None
    if catalog_ids is None:
        return ModelAdmission.refused(
            "openrouter_catalog_unavailable",
            "OpenRouter's public model catalog could not be read right now — "
            "this says nothing about whether the model exists; retry later",
        )
    if upstream not in catalog_ids:
        return ModelAdmission.refused(
            "model_not_on_openrouter",
            f"{upstream!r} is not in OpenRouter's public model catalog — "
            "check the id at https://openrouter.ai/models",
        )
    return ModelAdmission.granted(
        ModelEntry(model_name=model_id, litellm_params={"model": model_id})
    )
