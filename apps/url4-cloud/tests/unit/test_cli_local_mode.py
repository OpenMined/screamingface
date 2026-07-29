"""`url4-cloud serve --local` selects local mode, and nothing else does.

Local mode fuses the control plane with the run mode and tolerates the insecure default JWT
secret, so which argv reaches it is a security boundary, not a convenience. The cases that matter
are the ones where it must NOT be chosen — a bare `url4-cloud` (the image CMD and the chart's
Deployment command) above all.

Self-contained by design: its own fixture rather than one imported from `test_cli.py`, so the
suites stay independently readable and neither has to change when the other grows.
"""

import pytest

from url4_cloud import cli


@pytest.fixture
def modes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which entrypoint `main` selects, without entering any of them for real."""
    called: list[str] = []
    monkeypatch.setattr(cli, "_serve", lambda: called.append("serve"))
    monkeypatch.setattr(cli, "_serve_local", lambda: called.append("serve-local"))
    monkeypatch.setattr(cli, "_run", lambda: called.append("run"))
    return called


def test_serve_local_selects_local_mode(modes: list[str]) -> None:
    cli.main(["serve", "--local"])
    assert modes == ["serve-local"]


def test_bare_argv_is_never_local(modes: list[str]) -> None:
    """INVARIANT: this is the image's `CMD ["url4-cloud"]`.

    Falling into local mode here would mean a deployed App serving on the publicly-known dev JWT
    secret, with runs executing inside the control-plane process.
    """
    cli.main([])
    assert modes == ["serve"]


def test_plain_serve_is_never_local(modes: list[str]) -> None:
    cli.main(["serve"])
    assert modes == ["serve"]


def test_run_mode_rejects_the_local_flag(modes: list[str]) -> None:
    """`run` has no `--local`: a Job either executes its one expression or it does not."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--local"])

    assert exc.value.code == 2
    assert modes == []


def test_local_resolves_the_real_local_app_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_serve_local` itself, unshimmed — so its lazy imports are proven to resolve.

    The tests above replace `_serve_local` wholesale, which would keep passing even if it named a
    module or factory that no longer exists. This patches uvicorn instead, so a rename in
    `url4_cloud.local` fails here rather than at a developer's first `--local` boot.
    """
    import uvicorn

    captured: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(app=app, **kw))

    cli._serve_local()

    from url4_cloud.local import LOCAL_HOST, create_local_app

    assert captured["app"] == "url4_cloud.local:create_local_app"
    assert captured["factory"] is True
    # INVARIANT: loopback. Not configurable, and never 0.0.0.0 — see `local.LOCAL_HOST`.
    assert captured["host"] == LOCAL_HOST == "127.0.0.1"
    assert callable(create_local_app)
