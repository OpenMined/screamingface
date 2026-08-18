from screamingface_engine.runner.connector import AigatewayConfig


def test_default_model_matches_aigateways_unprefixed_anthropic_catalog_shape() -> None:
    assert AigatewayConfig().default_model == "claude-haiku-4-5"
