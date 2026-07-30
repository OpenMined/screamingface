"""Hugging Face discovery cardinality limits."""

from __future__ import annotations

import pytest

from aigateway.core.parameter_discovery import DiscoveryError
from aigateway.plugins.huggingface_provider.discovery import parse_hf_backend_capabilities


def test_router_model_count_is_bounded() -> None:
    catalog = {"data": [{"id": f"org/model-{index}"} for index in range(10_001)]}

    with pytest.raises(DiscoveryError) as excinfo:
        parse_hf_backend_capabilities(
            catalog,
            upstream_model_id="org/model-0",
            backend="cerebras",
        )

    assert excinfo.value.reason == "model_catalog_too_large"


def test_backend_count_per_model_is_bounded() -> None:
    catalog = {
        "data": [
            {
                "id": "org/model",
                "providers": [{"provider": f"backend-{index}"} for index in range(513)],
            }
        ]
    }

    with pytest.raises(DiscoveryError) as excinfo:
        parse_hf_backend_capabilities(
            catalog,
            upstream_model_id="org/model",
            backend="backend-0",
        )

    assert excinfo.value.reason == "provider_catalog_too_large"
