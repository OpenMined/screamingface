import pytest

from screamingface.plugins.url4_executor.ensemble_helpers import resolve_ensemble
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.tests.test_ensemble import _FakeDispatchPlugin, _make_app
from screamingface.plugins.url4_executor.url4 import Url4List
from screamingface.plugins.url4_executor.url4_grammar import parse


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
