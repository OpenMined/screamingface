import pytest

from screamingface.plugins.claude_frontend._classifier import (
    AUX_STUB_TEXT,
    is_auxiliary_request,
    is_cc_main_loop,
    is_utility_model,
)
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings

UTIL = ["haiku"]


def test_settings_defaults_enable_aux_filtering():
    s = ClaudeFrontendSettings()
    assert s.filter_auxiliary_requests is True
    assert s.utility_models == ["haiku"]


def test_settings_utility_models_can_be_cleared():
    # A user who runs Haiku as their MAIN model can disable model-based filtering.
    s = ClaudeFrontendSettings(utility_models=[])
    assert s.utility_models == []


@pytest.mark.parametrize(
    "model",
    [
        "claude-3-5-haiku-20241022",
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
        "CLAUDE-HAIKU-4-5",
    ],
)
def test_haiku_models_match_utility(model):
    assert is_utility_model(model, UTIL) is True


@pytest.mark.parametrize("model", ["claude-opus-4-1-20250805", "claude-sonnet-4-5", ""])
def test_non_haiku_models_do_not_match_utility(model):
    assert is_utility_model(model, UTIL) is False


def test_empty_utility_list_matches_nothing():
    assert is_utility_model("claude-haiku-4-5", []) is False


@pytest.mark.parametrize("model", [123, ["x"], {}, None])
def test_non_string_model_is_never_auxiliary(model):
    # The classifier runs on the raw, unvalidated request body; a non-string model
    # must fall through safely (→ /ensemble), never raise.
    body = {"model": model, "messages": [{"role": "user", "content": "quota"}]}
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=True) is False


def test_cc_identity_in_system_is_main_loop():
    body = {"system": [{"type": "text", "text": "You are Claude Code, Anthropic's official CLI."}]}
    assert is_cc_main_loop(body) is True


def test_string_system_with_identity_is_main_loop():
    body = {"system": "You are Claude Code, Anthropic's official CLI for Claude."}
    assert is_cc_main_loop(body) is True


def test_nonempty_tools_is_main_loop():
    body = {"system": "Generate a title.", "tools": [{"name": "Bash"}]}
    assert is_cc_main_loop(body) is True


def test_aux_probe_is_not_main_loop():
    body = {
        "system": "Generate a concise title for this conversation.",
        "messages": [{"role": "user", "content": "x"}],
    }
    assert is_cc_main_loop(body) is False


def test_haiku_aux_probe_is_auxiliary():
    body = {
        "model": "claude-haiku-4-5",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "quota"}],
    }
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=True) is True


def test_haiku_MAIN_LOOP_turn_is_NOT_auxiliary():
    body = {
        "model": "claude-haiku-4-5-20251001",
        "system": [
            {"type": "text", "text": "x-anthropic-billing-header: cc_entrypoint=cli; cch=fa1;"},
            {"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude."},
        ],
        "tools": [{"name": "Bash"}],
        "messages": [{"role": "user", "content": "real question"}],
    }
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=True) is False


def test_opus_turn_is_never_auxiliary():
    body = {"model": "claude-opus-4-1-20250805", "messages": [{"role": "user", "content": "hi"}]}
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=True) is False


def test_disabled_filtering_is_never_auxiliary():
    body = {"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "quota"}]}
    assert is_auxiliary_request(body, utility_models=UTIL, enabled=False) is False


def test_empty_utility_models_is_never_auxiliary():
    body = {"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "quota"}]}
    assert is_auxiliary_request(body, utility_models=[], enabled=True) is False


def test_stub_text_is_empty_str():
    assert AUX_STUB_TEXT == ""
