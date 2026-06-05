from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings


def test_settings_defaults_enable_aux_filtering():
    s = ClaudeFrontendSettings()
    assert s.filter_auxiliary_requests is True
    assert s.utility_models == ["haiku"]


def test_settings_utility_models_can_be_cleared():
    # A user who runs Haiku as their MAIN model can disable model-based filtering.
    s = ClaudeFrontendSettings(utility_models=[])
    assert s.utility_models == []
