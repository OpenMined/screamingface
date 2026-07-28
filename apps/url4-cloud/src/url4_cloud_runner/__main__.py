"""Runner Job entrypoint — read env, wire ``NatsBus`` + executor, run the lifecycle (spec §1.1/§9).

The k8s/Docker JobRunner (OME-519) injects ``URL4_CLOUD_TOPIC`` / ``URL4_CLOUD_EXPRESSION`` /
``URL4_CLOUD_NATS_URL``. :func:`params_from_env` is the pure, unit-tested parse; :func:`main` is the
network/event-loop glue (NatsBus + ``asyncio.run``), excluded from coverage per the INFRA rule.
"""

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass

from url4_cloud_nats import NatsBus
from url4_cloud_runner.executor import MockExecutor
from url4_cloud_runner.publish import run

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


def main() -> None:  # pragma: no cover - real NATS + event loop (INFRA rule)
    params = params_from_env(os.environ)
    # WHY: MockExecutor is the interim engine channel until the real url4 seam (OME-446) lands.
    asyncio.run(run(NatsBus(params.nats_url), MockExecutor(), params.topic, params.url4))


if __name__ == "__main__":  # pragma: no cover
    main()
