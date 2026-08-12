"""Local mode installs Benchmarks only where their assets were declared.

FEATURE: local bring-up — `url4-cloud serve --local` on a clean checkout.
STORY: as a developer with a fresh clone, I evaluate a single-model expression without first
obtaining the 100-case DRACO asset bundle that exists only inside the deployed image.

WHY this is worth a guard: `benchmarks.install()` runs while the WORLD is built, before and
independent of what the expression addresses, so a benchmark whose assets are absent fails EVERY
run — including runs that reference no benchmark at all. The failure surfaces as
`benchmark_unavailable`, which reads like a benchmark problem and is really a packaging one.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI

from url4_cloud.benchmarks import EMPTY_BENCHMARKS
from url4_cloud.benchmarks.builtins import BUILTIN_BENCHMARKS
from url4_cloud.benchmarks.registry import BENCHMARK_ASSETS_ENV
from url4_cloud.config import Settings
from url4_cloud.local import create_local_app


def _app(env: Mapping[str, str], **kwargs: object) -> FastAPI:
    return create_local_app(Settings(jwt_secret="s" * 32, **kwargs), env=env)  # type: ignore[arg-type]


def _installed(app: FastAPI):
    """The registry the App handed the executor factory — what a run would install."""
    return app.state.job_runner._factory.keywords["benchmarks"]  # noqa: SLF001


def test_a_checkout_that_declares_no_asset_root_installs_no_benchmarks() -> None:
    # INVARIANT: local mode never installs a Benchmark whose assets it was not pointed at.
    # This is what keeps an unrelated expression from dying on a missing DRACO case file.
    assert len(_installed(_app({}))) == 0


def test_declaring_an_asset_root_opts_back_into_the_builtins() -> None:
    # WHY the env var is the switch: naming an asset root is the operator stating the assets
    # exist. Local mode takes them at their word and installs — so a bogus path fails loudly
    # rather than silently serving a Benchmark-less Engine.
    installed = _installed(_app({BENCHMARK_ASSETS_ENV: "/opt/benchmarks"}))

    assert installed is BUILTIN_BENCHMARKS


def test_an_explicitly_passed_registry_outranks_the_env_default() -> None:
    # INVARIANT: the parameter is the caller's decision; the env only fills its absence.
    app = create_local_app(
        Settings(jwt_secret="s" * 32),
        env={BENCHMARK_ASSETS_ENV: "/opt/benchmarks"},
        benchmarks=EMPTY_BENCHMARKS,
    )

    assert _installed(app) is EMPTY_BENCHMARKS
