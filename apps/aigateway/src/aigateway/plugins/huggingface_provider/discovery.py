"""OME-479 §6.2 — Hugging Face public-catalog parsers (PURE).

FEATURE: Hugging Face P0 observation overlay. Two kinds of evidence, kept apart:

- BACKEND-CONDITIONAL capability from the FIXED public router catalog
  (`/v1/models`): for the selected backend, the tool / structured-output / modality
  facts (source label ``huggingface:router``);
- labelled-static PARAMETER evidence (``huggingface:static``): the standard sampling
  fields the INSTALLED litellm ``HuggingFaceChatConfig`` transform accepts, used as
  the detail contract's observation source. HF's catalog carries NO parameter list
  (§5.1), so parameters can only come from this labelled-static fallback.

INVARIANT (SOLID/hexagonal): pure functions over an already-fetched, already-bounded
document — NO network, NO clock, NO credentials here. The bounded transport
(``core/parameter_discovery``) supplies the document; this module only parses it.
INVARIANT (§5.1): capability and parameter evidence carry DISTINCT source labels.
INVARIANT (§5.3): a model or backend absent from the catalog yields ``None`` —
honest absence, never fabricated support.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aigateway.core.chat_parameters import ProviderParameterObservation

# Fixed public source (the async fetch step passes this to the bounded transport;
# the parsers below never dereference a URL themselves).
MODELS_URL = "https://router.huggingface.co/v1/models"
ALLOWED_ORIGINS: frozenset[str] = frozenset({"https://router.huggingface.co"})

# Live catalog capability evidence vs labelled-static parameter evidence — DISTINCT
# provenance so a reader can tell network-derived capability from a reviewed-static
# parameter fallback (§5.1 "labelled").
ROUTER_SOURCE = "huggingface:router"
STATIC_SOURCE = "huggingface:static"


@dataclass(frozen=True)
class HfBackendCapabilities:
    """Per-BACKEND capability facts for one model row (§6.2 backend-conditional).

    # INVARIANT: a capability absent from the backend row stays ``None`` (UNKNOWN),
    # never coerced to ``False`` — the catalog lists positive support, and silence
    # is not a negative verdict.
    """

    input_modalities: tuple[str, ...]
    output_modalities: tuple[str, ...]
    supports_tools: bool | None
    supports_structured_output: bool | None


def _modalities(architecture: Any, key: str) -> tuple[str, ...]:
    if not isinstance(architecture, Mapping):
        return ()
    values = architecture.get(key)
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, str))


def _bool_or_none(value: Any) -> bool | None:
    # WHY: only a genuine JSON boolean is a verdict; anything else is UNKNOWN.
    return value if isinstance(value, bool) else None


def parse_hf_backend_capabilities(
    catalog: Any, *, upstream_model_id: str, backend: str
) -> HfBackendCapabilities | None:
    """Capability facts for one model+backend, or ``None`` if either is absent.

    The catalog keys rows by the bare ``<org>/<model>`` id; the ``:<provider>``
    backend is one entry in that row's ``providers[]`` array. Support is read from
    the SELECTED backend only, so the verdict is backend-conditional (§6.2).
    """
    if not isinstance(catalog, Mapping):
        return None
    data = catalog.get("data")
    if not isinstance(data, list):
        return None
    row = next(
        (m for m in data if isinstance(m, Mapping) and m.get("id") == upstream_model_id),
        None,
    )
    if row is None:
        return None
    providers = row.get("providers")
    if not isinstance(providers, list):
        return None
    entry = next(
        (p for p in providers if isinstance(p, Mapping) and p.get("provider") == backend),
        None,
    )
    if entry is None:
        return None
    architecture = row.get("architecture")
    return HfBackendCapabilities(
        input_modalities=_modalities(architecture, "input_modalities"),
        output_modalities=_modalities(architecture, "output_modalities"),
        supports_tools=_bool_or_none(entry.get("supports_tools")),
        supports_structured_output=_bool_or_none(entry.get("supports_structured_output")),
    )


# OME-479 §6.2 — labelled-static PARAMETER evidence (NO network). The standard
# OpenAI sampling fields the INSTALLED litellm ``HuggingFaceChatConfig`` transform
# (a subclass of ``OpenAIGPTConfig``) accepts and forwards — verified against the
# installed transform's ``get_supported_openai_params`` / ``transform_request``. HF
# has no native ``top_k``, so it is intentionally NOT listed (honest absence). Tool
# capabilities live in their own contract section, so ``tools`` / ``tool_choice``
# are intentionally excluded here.
# AIDEV-NOTE: reviewed labelled-static evidence, not a central inventory — extend
# only for a field the installed transform provably accepts.
_STATIC_PARAM_NAMES: tuple[str, ...] = (
    "temperature",
    "top_p",
    "max_tokens",
    "frequency_penalty",
    "presence_penalty",
    "seed",
    "stop",
)


def _observation(name: str) -> ProviderParameterObservation:
    return ProviderParameterObservation(
        request_path=name, support="supported", source=STATIC_SOURCE
    )


HF_STATIC_PARAM_OBSERVATIONS: tuple[ProviderParameterObservation, ...] = tuple(
    _observation(name) for name in sorted(_STATIC_PARAM_NAMES)
)
