"""Runner Job entrypoint — read env, wire ``NatsBus`` + executor, run the lifecycle (spec §1.1/§9).

The k8s/Docker JobRunner (OME-519) injects ``URL4_CLOUD_TOPIC`` / ``URL4_CLOUD_EXPRESSION`` /
``URL4_CLOUD_NATS_URL``, plus — when the caller forwarded an aigateway credential (identity
forwarding, plan §5.3 dec:A) — ``AIGATEWAY_TOKEN`` / ``AIGATEWAY_PROFILE`` / ``AIGATEWAY_BASE_URL``
/ ``AIGATEWAY_MODEL``. :func:`params_from_env` and :func:`build_executor` are the pure, unit-tested
parses; :func:`main` is the network/event-loop glue (NatsBus + ``asyncio.run``), excluded from
coverage per the INFRA rule.
"""

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace

import httpx

from url4_cloud_nats import NatsBus
from url4_cloud_runner.aigateway_connector import AigatewayConfig, build_aigateway_world
from url4_cloud_runner.publish import run
from url4_cloud_runner.url4_executor import Url4Executor, deny_by_default_world

_DEFAULT_NATS_URL = "nats://localhost:4222"


class RunnerConfigError(Exception):
    """A required Runner environment variable is missing."""


@dataclass(frozen=True)
class RunnerParams:
    """The Runner Job's inputs, read from its environment."""

    topic: str
    url4: str
    nats_url: str


def params_from_env(environ: Mapping[str, str]) -> RunnerParams:
    """Parse the Runner Job's env into :class:`RunnerParams`; raise on a missing required var."""
    try:
        topic = environ["URL4_CLOUD_TOPIC"]
        url4 = environ["URL4_CLOUD_EXPRESSION"]
    except KeyError as exc:
        raise RunnerConfigError(f"missing required runner env var: {exc.args[0]}") from exc
    return RunnerParams(
        topic=topic,
        url4=url4,
        nats_url=environ.get("URL4_CLOUD_NATS_URL", _DEFAULT_NATS_URL),
    )


async def build_executor(
    env: Mapping[str, str],
    *,
    client: httpx.AsyncClient | None = None,
    tavily_client: httpx.AsyncClient | None = None,
) -> Url4Executor:
    """Build the Runner's :class:`Url4Executor` (identity forwarding, plan §5.3 dec:A).

    ``AIGATEWAY_TOKEN`` present → the aigateway connector world (:func:`build_aigateway_world`),
    with ``AIGATEWAY_PROFILE``/``AIGATEWAY_BASE_URL``/``AIGATEWAY_MODEL`` as optional overrides
    (falling back to :class:`~url4_cloud_runner.aigateway_connector.AigatewayConfig`'s own
    defaults); the world's client is closed on run teardown via ``Url4Executor``'s
    ``world_aclose`` hook. Absent → the deny-by-default world, unchanged from before this batch.

    Web tools (spec 2026-07-23, dec:W4): ``TAVILY_API_KEY`` present → forwarded as
    ``tavily_api_key=`` so the connector declares ``web_search``/``web_fetch`` to the model
    and runs the bounded tool-calling loop; absent → ``web_tools_enabled`` stays ``False``
    (deny-by-default, dec:W5). ``TAVILY_API_KEY`` is a runner-level operator secret — never
    logged, treated like ``AIGATEWAY_SECRET_KEY``.

    ``client``/``tavily_client`` are test-only: forwarded verbatim to :func:`build_aigateway_world`
    so a headless test can inject ``httpx.MockTransport``-backed clients instead of real
    ``GET /v1/models`` / Tavily calls. Production callers (:func:`main`) never pass them.
    """
    token = env.get("AIGATEWAY_TOKEN")
    if not token:
        # WHY: deny-by-default world (empty StaticIOLayer — no routes/holdings/fetch_map) when no
        # aigateway credential was forwarded; Url4Executor is the OME-446 engine seam — the only
        # production Executor adapter.
        return Url4Executor(deny_by_default_world())
    # `dataclasses.replace` keeps the typed defaults and overrides only the env-supplied str
    # fields — a `**dict[str, str]` splat cannot be proven safe against the non-str config
    # fields (models/timeout_s/tavily_*/web_tool_max_iterations).
    cfg = AigatewayConfig()
    if "AIGATEWAY_BASE_URL" in env:
        cfg = replace(cfg, base_url=env["AIGATEWAY_BASE_URL"])
    if "AIGATEWAY_MODEL" in env:
        cfg = replace(cfg, default_model=env["AIGATEWAY_MODEL"])
    world = await build_aigateway_world(
        cfg,
        token=token,
        profile=env.get("AIGATEWAY_PROFILE"),
        client=client,
        tavily_api_key=env.get("TAVILY_API_KEY"),
        tavily_client=tavily_client,
    )
    return Url4Executor(world.node, world_aclose=world.aclose)


def main() -> None:  # pragma: no cover - real NATS + event loop (INFRA rule)
    async def _main() -> None:
        params = params_from_env(os.environ)
        executor = await build_executor(os.environ)
        traceparent = os.environ.get("URL4_CLOUD_TRACEPARENT")
        await run(
            NatsBus(params.nats_url), executor, params.topic, params.url4, traceparent=traceparent
        )

    asyncio.run(_main())


if __name__ == "__main__":  # pragma: no cover
    main()
