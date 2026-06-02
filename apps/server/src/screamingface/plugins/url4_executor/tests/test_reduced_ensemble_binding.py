import pytest

from screamingface.plugins.url4_executor.ensemble_helpers import resolve_ensemble
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.tests.test_ensemble import _FakeDispatchPlugin, _make_app
from screamingface.plugins.url4_executor.url4_ast import (
    Url4BackendCall,
    Url4Binding,
    Url4List,
    Url4Reduce,
    Url4Text,
)
from screamingface.plugins.url4_executor.url4_grammar import parse


def test_binding_value_group_with_intent_parses_to_reduce():
    node = parse(
        "(consensus=(claude:0.40:/claude(q)!'a', codex:0.30:/codex(q)!'b')!'reduce, weighted')"
    )
    assert isinstance(node, Url4List)
    binding = node.items[0]
    assert isinstance(binding, Url4Binding) and binding.name == "consensus"
    rv = binding.value
    assert isinstance(rv, Url4Reduce)
    assert len(rv.items) == 2 and all(isinstance(i, Url4BackendCall) for i in rv.items)
    assert isinstance(rv.intent, Url4Text)
    assert rv.intent.value == "'reduce, weighted'"  # quoted rule keeps the comma
    assert rv.broadcast is False


def test_bare_group_binding_still_parses_as_list():
    # regression: a group binding WITHOUT a trailing intent stays a Url4List
    node = parse("(x=(a, b))")
    assert isinstance(node, Url4List)
    binding = node.items[0]
    assert isinstance(binding, Url4Binding)
    assert isinstance(binding.value, Url4List)


@pytest.mark.asyncio
async def test_resolve_ensemble_fans_out_and_reduces():
    # 3 fan-out sources answer A/B/C; the processor (also /claude) returns the reduced answer.
    claude = _FakeDispatchPlugin(
        name="claude", paths=["/claude"], responses=["A", "B", "C", "REDUCED"]
    )
    app = _make_app(claude)
    group = parse(
        "(claude:0.40:/claude(q)!'a', claude:0.30:/claude(q)!'b', claude:0.30:/claude(q)!'c')"
    )
    assert isinstance(group, Url4List)
    out = await resolve_ensemble(
        group.items, "Combine these.", processor="/claude", app=app, env=Env.root()
    )
    assert out == "REDUCED"  # the processor's reduce output (4th /claude call)
    assert len(claude.calls) == 4  # 3 fan-out + 1 reduce
