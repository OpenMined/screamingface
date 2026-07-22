"""Regression checks for the local engine-to-Gateway trust boundary."""

from __future__ import annotations

from pathlib import Path

COMPOSE = Path(__file__).parents[1] / "apps" / "screamingface-engine" / "compose.yaml"

HF_MODELS = (
    "huggingface/openai/gpt-oss-120b:cerebras",
    "huggingface/Qwen/Qwen3-Coder-480B-A35B-Instruct:novita",
    "huggingface/deepseek-ai/DeepSeek-R1:novita",
    "huggingface/google/gemma-2-2b-it:featherless-ai",
    "huggingface/meta-llama/Llama-3.1-8B-Instruct:nscale",
    "huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra",
    "huggingface/zai-org/GLM-5.2:deepinfra",
)


def test_auth_disabled_gateway_is_reached_over_shared_loopback() -> None:
    source = COMPOSE.read_text()

    assert 'AIGATEWAY_AUTH_ENABLED: "0"' in source
    assert "AIGATEWAY_URL: http://127.0.0.1:9105" in source
    assert 'AIGATEWAY_TIMEOUT: "600"' in source
    assert 'SCREAMINGFACE_ENGINE_TIMEOUT: "1800"' in source
    assert 'AIGW_PROVIDER_MAX_CONCURRENCY: "32"' in source
    assert 'SCREAMINGFACE_ENGINE_URL4_CONCURRENCY: "32"' in source
    assert 'SCREAMINGFACE_ENGINE_CASE_CONCURRENCY: "10"' in source
    assert 'SCREAMINGFACE_ENGINE_MODEL_CONCURRENCY: "32"' in source
    assert 'SCREAMINGFACE_ENGINE_SYNTHESIS_CONCURRENCY: "16"' in source
    assert 'SCREAMINGFACE_ENGINE_JUDGE_CONCURRENCY: "32"' in source
    assert "network_mode: service:aigateway" in source
    assert "AIGATEWAY_URL: http://aigateway:9105" not in source


def test_shared_network_namespace_owner_publishes_both_ports() -> None:
    source = COMPOSE.read_text()

    gateway_port = '"127.0.0.1:${AIGATEWAY_HOST_PORT:-9105}:9105"'
    engine_port = '"127.0.0.1:${SCREAMINGFACE_ENGINE_HOST_PORT:-4404}:4404"'
    assert source.count(gateway_port) == 1
    assert source.count(engine_port) == 1


def test_local_gateway_catalog_keeps_defaults_and_adds_verified_hf_tool_pins() -> None:
    source = COMPOSE.read_text()

    assert "AIGW_HUGGINGFACE_DEFAULT_MODELS:" in source
    for model in HF_MODELS:
        assert source.count(model) == 1
