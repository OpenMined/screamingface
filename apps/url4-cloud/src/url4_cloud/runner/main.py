"""The `url4-cloud run` entrypoint: reads its Job env, wires the executor and NATS publisher,
and drives one url4 run end to end via ``url4.streaming.lifecycle.run``.

Reached from :func:`url4_cloud.cli.main` — the same console script that serves the control
plane, entered with a different subcommand. Nothing here imports the serving half; see the
layering note in :mod:`url4_cloud.runner`.
"""

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from url4.streaming.lifecycle import run
from url4_cloud import job_env
from url4_cloud.adapters.jetstream import JetStreamPublisher
from url4_cloud.runner.config import (
    AigatewaySection,
    RunnerConfig,
    RunnerConfigError,
    load_config,
)
from url4_cloud.runner.connector import (
    AigatewayConfig,
    build_aigateway_world,
    build_local_world,
)
from url4_cloud.runner.executor import Url4Executor, World, deny_by_default_world


@dataclass(frozen=True)
class RunnerParams:
    """The per-run values read off the Job's env — topic, expression, NATS URL, deadline."""

    topic: str
    url4: str
    nats_url: str
    deadline_s: float | None = None


def _deadline_from_env(environ: Mapping[str, str]) -> float | None:
    """Parse the run's deadline; absent means unbounded.

    WHY the run enforces this itself when k8s already sets ``activeDeadlineSeconds``: the
    substrate's deadline kills the POD, which ends the process before it can publish anything —
    leaving the topic with no terminal frame and every subscriber waiting. Self-terminating first
    is what turns the deadline into a ``Terminated(timed_out)`` a client can actually observe.
    A malformed value is refused rather than silently treated as unbounded.
    """
    raw = environ.get(job_env.JOB_DEADLINE_S)
    if raw is None:
        return None
    try:
        deadline = float(raw)
    except ValueError as exc:
        raise RunnerConfigError(f"{job_env.JOB_DEADLINE_S} is not a number: {raw!r}") from exc
    if deadline <= 0:
        raise RunnerConfigError(f"{job_env.JOB_DEADLINE_S} must be positive, got {deadline}")
    return deadline


def params_from_env(environ: Mapping[str, str]) -> RunnerParams:
    """Read the required per-run env vars, turning a missing one into ``RunnerConfigError``."""
    try:
        topic = environ[job_env.TOPIC]
        url4 = environ[job_env.EXPRESSION]
    except KeyError as exc:
        raise RunnerConfigError(f"missing required runner env var: {exc.args[0]}") from exc
    return RunnerParams(
        topic=topic,
        url4=url4,
        nats_url=environ.get(job_env.NATS_URL, job_env.DEFAULT_NATS_URL),
        deadline_s=_deadline_from_env(environ),
    )


def build_executor(
    env: Mapping[str, str],
    config: RunnerConfig | None = None,
    *,
    client: httpx.AsyncClient | None = None,
    tavily_client: httpx.AsyncClient | None = None,
) -> Url4Executor:
    """Wire an executor over the DECLARED world — without building it yet.

    The world is resolved on first ``execute`` (see ``Url4Executor._resolve_world``), so a bad
    config or an unreachable gateway surfaces as a Terminated(failed) frame on the topic
    rather than as a silent Job crash before the stream exists.

    ``client`` and ``tavily_client`` are test-only injection seams: production callers leave
    them ``None`` and let ``build_aigateway_world`` construct its own ``httpx.AsyncClient``(s);
    tests pass a fake/mocked client to avoid real network calls.

    ``job_env.TAVILY_API_KEY`` is an operator secret, handled the same way as
    ``AIGATEWAY_SECRET_KEY`` — never logged. It is read here and forwarded to
    ``build_aigateway_world`` as ``tavily_api_key``; when it is unset, the built world disables
    the web-search/web-fetch tool loop entirely (deny-by-default — see
    ``connector._build_tavily_client``), rather than leaving it half-configured.
    """

    async def _world() -> World:
        resolved = config if config is not None else load_config(env)
        section = resolved.aigateway
        if section is None:
            # WHY: a world with no [aigateway] table is a legitimate world, not necessarily an
            # empty one — a Job may declare only `[commands]` and/or `[data]` and never call a
            # model. With none of the three, the node denies everything undeclared, as always.
            if resolved.commands or resolved.data:
                return build_local_world(resolved.commands, resolved.data), None
            return deny_by_default_world(), None
        # WHY no credential check here any more: aigateway runs `cloudflare_headers` when deployed
        # and `disabled` locally, and NEITHER mode reads `Authorization` — so there is no token to
        # demand. Identity is forwarded when present and simply absent locally, where every caller
        # is anonymous. The old unconditional token requirement made every deployed run fail
        # before it issued a single request, because a deployed caller has no way to obtain one.
        world = await build_aigateway_world(
            aigateway_config_from(section),
            profile=env.get(job_env.AIGATEWAY_PROFILE),
            identity_headers=job_env.identity_from_env(env),
            client=client,
            tavily_api_key=env.get(job_env.TAVILY_API_KEY),
            tavily_client=tavily_client,
            commands=resolved.commands,
            data=resolved.data,
        )
        return world.node, world.aclose

    return Url4Executor(world_factory=_world)


def aigateway_config_from(section: AigatewaySection) -> AigatewayConfig:
    """Project a parsed `[aigateway]` table onto the connector's config.

    # AIDEV-NOTE: EVERY declarable field must be copied here. This was a field-by-field literal
    # inline in `_world`, and `web_tool_max_iterations` was simply absent from it — so the
    # connector's default of 5 was unreachable from any `url4.toml`, and MEASURED 2026-08-02 that
    # default is a hard per-case failure on the Tavily loop. A parsed field that no projection
    # copies is indistinguishable from one that was never declared: the config validates, the run
    # starts, and the value silently is not the one the operator wrote. Adding a field to
    # `AigatewaySection` without adding it here is the same bug again.
    """
    return AigatewayConfig(
        base_url=section.base_url,
        default_model=section.default_model,
        models=section.models,
        allow_outbound=section.allow_outbound,
        timeout_s=section.timeout_s,
        web_tool_max_iterations=section.web_tool_max_iterations,
    )


def main() -> None:  # pragma: no cover - real NATS + event loop (INFRA rule)
    async def _main() -> None:
        params = params_from_env(os.environ)
        executor = build_executor(os.environ)
        traceparent = os.environ.get(job_env.TRACEPARENT)
        await run(
            JetStreamPublisher(params.nats_url),
            executor,
            params.topic,
            params.url4,
            traceparent=traceparent,
            deadline_s=params.deadline_s,
        )

    asyncio.run(_main())


if __name__ == "__main__":  # pragma: no cover
    main()
