import pytest

from screamingface.plugins.url4_executor.ensemble_helpers import substitute_env_vars
from screamingface.plugins.url4_executor.scope import Env


def test_substitutes_named_binding_from_env():
    env = Env.root().child(consensus="Paris")
    assert substitute_env_vars("answer: $consensus", env) == "answer: Paris"


def test_substitutes_multiple_and_leaves_unknown():
    env = Env.root().child(consensus="B")
    assert substitute_env_vars("$consensus then $missing", env) == "B then $missing"


def test_item_is_reserved_but_item_id_resolves():
    env = Env.root().child(item_id="Y")  # no "item" key
    # $item_id resolves; bare $item is reserved (left for substitute_item)
    assert substitute_env_vars("$item_id and $item", env) == "Y and $item"


def test_non_string_value_is_stringified():
    env = Env.root().child(weight=0.4)
    assert substitute_env_vars("w=$weight", env) == "w=0.4"


def test_no_env_or_no_dollar_is_noop():
    assert substitute_env_vars("plain text", None) == "plain text"
    assert substitute_env_vars("", Env.root()) == ""


def test_substitutes_two_bindings_in_one_string():
    env = Env.root().child(consensus="B", normalized="high")
    assert substitute_env_vars("pick=$consensus dist=$normalized", env) == "pick=B dist=high"


def test_resolves_from_parent_scope():
    env = Env.root().child(consensus="X").child(other="Y")
    assert substitute_env_vars("$consensus", env) == "X"


@pytest.mark.asyncio
async def test_resolve_intent_substitutes_env_var():
    from screamingface.plugins.url4_executor.interpreter import resolve_intent

    env = Env.root().child(consensus="B")
    assert await resolve_intent("'pick $consensus'", None, env) == "pick B"


@pytest.mark.asyncio
async def test_dispatch_substitutes_env_var_in_payload():
    from screamingface.plugins.url4_executor.tests.test_ensemble import (
        _FakeDispatchPlugin,
        _make_app,
    )
    from screamingface.plugins.url4_executor.url4 import parse
    from screamingface.plugins.url4_executor.url4_ast import Url4BackendCall
    from screamingface.plugins.url4_executor.url4_resolve import _dispatch_backend_call

    py = _FakeDispatchPlugin(name="python-runner", paths=["/python"], responses=["ECHO"])
    app = _make_app(py)
    node = parse('/python(/data/code/x.py)!{"c":"$consensus"}')
    assert isinstance(node, Url4BackendCall)
    env = Env.root().child(consensus="B")
    await _dispatch_backend_call(node, app, env)
    intent_seen = py.calls[0][0]  # (intent, sources, app)
    assert intent_seen == '{"c":"B"}'
