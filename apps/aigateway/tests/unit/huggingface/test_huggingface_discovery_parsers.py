"""Phase 7a (OME-479 §5.1/§6.2): Hugging Face public-catalog parsers (PURE).

FEATURE: Hugging Face P0 observation overlay. Turns the FIXED public HF router
catalog into backend-conditional capability evidence, and exposes the labelled-
static chat-parameter evidence (the params the installed litellm transform
accepts — HF's catalog carries NO parameter list, §5.1).

INVARIANT (§5.1): endpoint/param evidence (`huggingface:static`) and live catalog
capability evidence (`huggingface:router`) carry DISTINCT source labels.
INVARIANT (§6.2): support is BACKEND-CONDITIONAL — two providers of the same model
can differ on tools/structured-output; the parser reports the selected backend's.
INVARIANT (§5.3): a model or backend missing from the catalog yields NO capability
(honest absence), never fabricated support.
"""

from __future__ import annotations

from aigateway.plugins.huggingface_provider.discovery import (
    HF_STATIC_PARAM_OBSERVATIONS,
    STATIC_SOURCE,
    HfBackendCapabilities,
    parse_hf_backend_capabilities,
)

# A faithful slice of the LIVE `https://router.huggingface.co/v1/models` shape:
# rows keyed by bare `<org>/<model>` id, modalities under `architecture`, and a
# `providers[]` array whose entries are the per-BACKEND capability rows. There is
# deliberately NO `supported_parameters` field anywhere — that is the real shape.
_CATALOG = {
    "object": "list",
    "data": [
        {
            "id": "openai/gpt-oss-120b",
            "object": "model",
            "owned_by": "openai",
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "providers": [
                {
                    "provider": "cerebras",
                    "status": "live",
                    "context_length": 131072,
                    "supports_tools": True,
                    "supports_structured_output": True,
                },
                {
                    "provider": "together",
                    "status": "live",
                    "context_length": 65536,
                    "supports_tools": False,
                    "supports_structured_output": False,
                },
            ],
        },
        {
            "id": "meta-llama/Llama-3.1-8B-Instruct",
            "object": "model",
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
            "providers": [
                {"provider": "nscale", "status": "live", "supports_tools": True},
            ],
        },
    ],
}


def test_parses_selected_backend_capabilities() -> None:
    caps = parse_hf_backend_capabilities(
        _CATALOG, upstream_model_id="openai/gpt-oss-120b", backend="cerebras"
    )
    assert isinstance(caps, HfBackendCapabilities)
    assert caps.input_modalities == ("text",)
    assert caps.output_modalities == ("text",)
    assert caps.supports_tools is True
    assert caps.supports_structured_output is True


def test_support_is_backend_conditional() -> None:
    # SAME model, DIFFERENT backend → different capability verdict (§6.2). This is
    # the property plan §9 "Hugging Face" requires: backend-conditional support.
    cerebras = parse_hf_backend_capabilities(
        _CATALOG, upstream_model_id="openai/gpt-oss-120b", backend="cerebras"
    )
    together = parse_hf_backend_capabilities(
        _CATALOG, upstream_model_id="openai/gpt-oss-120b", backend="together"
    )
    assert cerebras is not None and together is not None
    assert cerebras.supports_tools is True
    assert together.supports_tools is False
    assert cerebras.supports_structured_output is True
    assert together.supports_structured_output is False


def test_modalities_captured_per_model() -> None:
    caps = parse_hf_backend_capabilities(
        _CATALOG, upstream_model_id="meta-llama/Llama-3.1-8B-Instruct", backend="nscale"
    )
    assert caps is not None
    assert caps.input_modalities == ("text", "image")
    # a capability absent from the backend row stays UNKNOWN, never fabricated False.
    assert caps.supports_structured_output is None


def test_unknown_model_yields_none() -> None:
    assert (
        parse_hf_backend_capabilities(
            _CATALOG, upstream_model_id="nobody/nonexistent", backend="cerebras"
        )
        is None
    )


def test_known_model_unknown_backend_yields_none() -> None:
    # the model exists but is not offered by this backend → honest absence, not a
    # fabricated capability for a backend the router does not list.
    assert (
        parse_hf_backend_capabilities(
            _CATALOG, upstream_model_id="openai/gpt-oss-120b", backend="no-such-backend"
        )
        is None
    )


def test_malformed_catalog_yields_none() -> None:
    assert parse_hf_backend_capabilities([], upstream_model_id="a/b", backend="x") is None
    assert (
        parse_hf_backend_capabilities({"data": "nope"}, upstream_model_id="a/b", backend="x")
        is None
    )


def test_static_param_observations_are_labelled_static_sampling_fields() -> None:
    # PARAMETER evidence is labelled-static (the installed transform's accepted
    # sampling fields), NOT from the catalog — HF's catalog has no param list.
    paths = {o.request_path for o in HF_STATIC_PARAM_OBSERVATIONS}
    assert paths == {
        "temperature",
        "top_p",
        "max_tokens",
        "frequency_penalty",
        "presence_penalty",
        "seed",
        "stop",
    }
    for obs in HF_STATIC_PARAM_OBSERVATIONS:
        assert obs.source == STATIC_SOURCE == "huggingface:static"
        assert obs.support == "supported"
    # deterministic, deduplicated ordering (sorted by path).
    assert [o.request_path for o in HF_STATIC_PARAM_OBSERVATIONS] == sorted(paths)


def test_static_observations_exclude_top_k() -> None:
    # honesty vs OpenRouter: the installed HF transform does NOT accept top_k, so it
    # is never observed here (no fabricated support for an unsupported native field).
    assert all(o.request_path != "top_k" for o in HF_STATIC_PARAM_OBSERVATIONS)
    assert all("top_k" not in o.request_path for o in HF_STATIC_PARAM_OBSERVATIONS)
