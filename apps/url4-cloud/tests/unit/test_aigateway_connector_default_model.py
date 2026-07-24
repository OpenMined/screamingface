"""``AigatewayConfig.default_model``'s field default must match aigateway's real catalog shape.

FEATURE: a Runner boots with no ``AIGATEWAY_MODEL`` override — the everyday case (`__main__.py`
only sets ``default_model`` when that env var is present) — and must still build a valid world.

INVARIANT: aigateway's Anthropic entries are UNPREFIXED in ``GET /v1/models``
(``claude-opus-4-8``, ``claude-haiku-4-5``, ...) — only non-Anthropic providers carry a
``<provider>/`` prefix (``openrouter/...``, ``codex/...``, ``gemini-cli/...``,
``huggingface/...``). The old default, ``"anthropic/claude-haiku-4-5"``, assumed a prefix
Anthropic never gets — every unit test in ``test_aigateway_connector.py`` passes an explicit,
self-consistent ``default_model`` + mock catalog pair, so this mismatch was invisible to the
whole suite. Observed live: real catalog rejects it —
``ValueError: default_model 'anthropic/claude-haiku-4-5' is not in the aigateway catalog
[...'claude-haiku-4-5'...]`` — so every Runner Job with a forwarded credential and no
``AIGATEWAY_MODEL`` override crashed at world-build time, before touching the url4 expression.
"""

from url4_cloud_runner.aigateway_connector import AigatewayConfig


def test_default_model_matches_aigateways_unprefixed_anthropic_catalog_shape() -> None:
    assert AigatewayConfig().default_model == "claude-haiku-4-5"
