"""`web_tool_max_iterations` is declarable, because 5 is a hard failure for a research answer.

FEATURE: a Runner Job declares how many tool-calling rounds an answering route may take.
STORY: as a benchmark author, a candidate on the Tavily loop must be able to finish a
deep-research answer instead of dying at an unreachable ceiling.

WHY this exists: `AigatewayConfig.web_tool_max_iterations` defaulted to 5 and `main.py` never
passed it, so NO Job could raise it. MEASURED 2026-08-02 against a live model and a live Tavily,
`openrouter/moonshotai/kimi-k2.6` exhausted all 5 rounds on tool calls and never emitted content
— for a TRIVIAL question whose sources were freely reachable (the control run: 3 searches +
2 fetches, then `ResolutionError`). DRACO is a deep-research benchmark and the owner's 2026-08-02
decision routes three of its models through this loop, so every one of their cases would have
failed rather than answered.

INVARIANT: the failure is LOUD (`ResolutionError`) rather than a short answer, so it degrades a
run to fewer scored cases instead of to a wrong score. That is the honest shape — and it is still
a failure, which is why the ceiling has to be reachable.
"""

from __future__ import annotations

import pytest

from url4_cloud.runner.config import RunnerConfigError, parse_config

_BASE = '[aigateway]\ndefault_route = "/a"\nmodels = ["a"]\n'


def _section(text: str):
    section = parse_config_text(text).aigateway
    assert section is not None
    return section


def parse_config_text(text: str):
    import tomllib

    return parse_config(tomllib.loads(text), {})


def test_the_iteration_cap_is_declarable() -> None:
    assert _section(_BASE + "web_tool_max_iterations = 12\n").web_tool_max_iterations == 12


def test_the_default_is_unchanged_when_absent() -> None:
    """A config that never mentions the cap behaves exactly as it did before it was declarable —
    the regression guard for every existing `url4.toml`."""
    assert _section(_BASE).web_tool_max_iterations == 5


@pytest.mark.parametrize("value", ["0", "-1"])
def test_a_non_positive_cap_is_rejected(value: str) -> None:
    """Zero rounds means the loop posts nothing and raises on the first pass — a world that can
    never answer, accepted at parse. Same fail-fast rule as `timeout_s`."""
    with pytest.raises(RunnerConfigError, match="web_tool_max_iterations"):
        _section(_BASE + f"web_tool_max_iterations = {value}\n")


def test_a_non_integer_cap_is_rejected() -> None:
    with pytest.raises(RunnerConfigError, match="web_tool_max_iterations"):
        _section(_BASE + 'web_tool_max_iterations = "many"\n')


def test_a_boolean_is_not_an_integer_here() -> None:
    """INVARIANT: `bool` IS an `int` subclass in Python, so `true` would otherwise parse as a cap
    of 1 — a world where every tool-using route fails on its second round, configured by someone
    who typed a flag."""
    with pytest.raises(RunnerConfigError, match="web_tool_max_iterations"):
        _section(_BASE + "web_tool_max_iterations = true\n")


def test_the_declared_cap_reaches_the_connector_config() -> None:
    """Parsing it is worth nothing if `main.py` drops it on the floor — which is exactly the bug
    this closes. The field existed and was unreachable for the whole life of the tool loop."""
    from url4_cloud.runner.main import aigateway_config_from

    section = _section(_BASE + "web_tool_max_iterations = 9\n")

    assert aigateway_config_from(section).web_tool_max_iterations == 9
