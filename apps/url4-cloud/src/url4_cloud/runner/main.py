"""The `url4-cloud run` entrypoint: reads its Job env, wires the executor and NATS publisher,
and drives one url4 run end to end via ``url4.streaming.lifecycle.run``.

Reached from :func:`url4_cloud.cli.main` — the same console script that serves the control
plane, entered with a different subcommand. Nothing here imports the serving half; see the
layering note in :mod:`url4_cloud.runner`.
"""

import asyncio
import os
import signal
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any

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

    INVARIANT: the projection is MECHANICAL — every field `AigatewaySection` declares is copied by
    construction, so a new `[aigateway]` key cannot be parsed and then dropped here.

    # AIDEV-NOTE: this was a field-by-field literal inline in `_world`, and
    # `web_tool_max_iterations` was simply absent from it — so the connector's default of 5 was
    # unreachable from any `url4.toml`, and MEASURED 2026-08-02 that default is a hard per-case
    # failure on the Tavily loop. A parsed field that no projection copies is indistinguishable
    # from one that was never declared: the config validates, the run starts, and the value
    # silently is not the one the operator wrote. Listing the fields again — even correctly —
    # leaves that bug one forgotten line away, which is why the names are read off the dataclass.
    #
    # `fields()` rather than `asdict()`: the latter deep-converts, which would turn each
    # `ModelSpec` into a plain dict and lose the declared route capabilities.
    #
    # The section is a NAME-FOR-NAME subset of `AigatewayConfig`; a field added to one and not the
    # other is a TypeError here, at Job boot, rather than a silently defaulted value at run time.
    """
    return AigatewayConfig(**{f.name: getattr(section, f.name) for f in fields(section)})


_CANCEL_SIGNALS: tuple[signal.Signals, ...] = (signal.SIGTERM,)
"""The signals that mean "the run is being cancelled".

SIGTERM is what a Runner Job actually receives: `JobRunner.stop` deletes the Job with
`propagation_policy="Background"`, the kubelet SIGTERMs the Pod, and SIGKILL follows once the
termination grace period expires.

INVARIANT: SIGINT is deliberately ABSENT. `asyncio.run` already installs its own SIGINT handler
(`asyncio.runners.Runner._on_sigint`) whose first action is to cancel the main task — the exact
cancellation this helper delivers for SIGTERM — so Ctrl-C on a local `url4-cloud run` already
produces the terminal frame. Handling it here would REPLACE that handler and take over its
interrupt counting, silently breaking the escalation where a second Ctrl-C force-quits a run
that will not stop.
"""


async def cancel_on_signal(
    coro: Coroutine[Any, Any, None],
    *,
    signals: Sequence[signal.Signals] = _CANCEL_SIGNALS,
) -> None:
    """Await ``coro``, turning a shutdown signal into a cancellation of it.

    FEATURE: cancelling an in-flight run (OME-315).
    STORY: as a user who cancelled a run, I need the stream to END, so my client stops waiting.

    WHY this exists: `lifecycle.run` already publishes `Terminated(stopped)` from its
    `except CancelledError` arm — but nothing ever delivered a cancellation here, so that arm
    never ran. The topic got no terminal frame at all: a subscriber waited forever, while
    `status()` reported the deleted Job as `not_found` — indistinguishable from a run that never
    existed. This is the same hazard `_deadline_from_env` names for `activeDeadlineSeconds`
    ("the substrate's deadline kills the POD, which ends the process before it can publish
    anything"), and it gets the same answer: self-terminate first, then let the process die.

    # AIDEV-NOTE: the handler is what makes the signal ARRIVE AT ALL here, not merely what makes
    # it useful. A Runner Job sets `command:`, which overrides the image's
    # `ENTRYPOINT ["tini", "--"]` — confirmed on a live Job, whose /proc/1/cmdline is
    # `url4-cloud run` — so this process is PID 1 with no init supervising it, and the kernel
    # does not apply DEFAULT signal actions to a PID-namespace init. SIGTERM was therefore
    # DISCARDED, and the Pod ran on until SIGKILL ended the grace period.
    #
    # MEASURED on kind 2026-08-03, same cluster and expression, only the runner image differing:
    #
    #   pre-fix   no terminal frame at all; DELETE waited out its full drain bound (5.014s) and
    #             gave up; Pod exit 137 (SIGKILL) 30s after the delete — the whole
    #             terminationGracePeriodSeconds spent ignoring the signal
    #   post-fix  `terminated: stopped` on the topic 27ms after the delete; Pod exit 0
    #             ("Completed"), no grace period burned
    #
    # So this also removes a 30-second teardown from every cancelled run. Keep the handler, not
    # an entrypoint change: tini would forward SIGTERM, but the default action still kills the
    # process before `lifecycle.run` can publish anything.

    # AIDEV-NOTE: `loop.add_signal_handler`, never `signal.signal`. A C-level handler runs
    # between bytecodes on an arbitrary stack and may not touch loop state; this one is
    # scheduled on the loop, where cancelling a task is safe. It is also why this lives in the
    # deployable rather than in `packages/url4` — installing process-wide signal handlers is the
    # entrypoint's call to make, never a library's.
    """
    loop = asyncio.get_running_loop()
    task = asyncio.create_task(coro)
    ours = False

    def _cancel_once() -> None:
        # INVARIANT: exactly ONE cancellation, however many signals arrive. The terminal frame is
        # published from inside the run's `except CancelledError` arm, and that publish awaits —
        # a second `task.cancel()` landing there raises straight through the arm's
        # `contextlib.suppress(Exception)`, because CancelledError is a BaseException. That
        # destroys the very frame the first signal existed to produce. Escalating a run that will
        # not stop is the substrate's job (SIGKILL after the grace period), not a second handler.
        nonlocal ours
        if ours:
            return
        ours = True
        task.cancel()

    for sig in signals:
        loop.add_signal_handler(sig, _cancel_once)
    try:
        await task
    except asyncio.CancelledError:
        # WHY absorbed rather than re-raised, against the usual rule: we ARE the canceller, and
        # this is the process boundary — propagating would exit non-zero with a traceback for a
        # shutdown that went exactly as asked. A cancellation we did NOT cause is someone else's
        # (an enclosing TaskGroup tearing down) and must still reach them, hence the guard.
        if not ours:
            raise
    finally:
        # A handler outliving its run would cancel whatever ran next on this loop.
        for sig in signals:
            loop.remove_signal_handler(sig)


def main() -> None:  # pragma: no cover - real NATS + event loop (INFRA rule)
    async def _main() -> None:
        params = params_from_env(os.environ)
        executor = build_executor(os.environ)
        traceparent = os.environ.get(job_env.TRACEPARENT)
        await cancel_on_signal(
            run(
                JetStreamPublisher(params.nats_url),
                executor,
                params.topic,
                params.url4,
                traceparent=traceparent,
                deadline_s=params.deadline_s,
            )
        )

    asyncio.run(_main())


if __name__ == "__main__":  # pragma: no cover
    main()
