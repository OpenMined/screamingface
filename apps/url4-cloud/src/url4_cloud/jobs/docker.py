"""``DockerJobRunner`` — the ``JobRunner`` over a run-once container (local/compose e2e; spec §11).

Docker has no Job kind; a run-once container named by :func:`job_name` stands in for the k8s Job so
prod (k8s) and e2e (compose) share the same code path. The ``docker.DockerClient`` is injected
(structurally, :class:`DockerContainersClient`) so tests drive a fake — no real daemon (INFRA rule).
"""

from collections.abc import Mapping, Sequence
from typing import Protocol

from docker.errors import NotFound

from url4_cloud.jobs.port import RUNNER_LABELS, JobAlreadyExists, JobStatus, job_name

# Container runtime states that are not yet a terminal exit (spec §3 non-terminal states).
_LIVE_STATES: dict[str, JobStatus] = {
    "created": "scheduled",
    "running": "running",
    "restarting": "running",
    "paused": "running",
    "removing": "stopped",
}


class _Container(Protocol):
    @property
    def status(self) -> str: ...
    @property
    def attrs(self) -> Mapping[str, object]: ...
    def remove(self, force: bool = False) -> object: ...


class _Containers(Protocol):
    def run(self, image: str, **kwargs: object) -> _Container: ...
    def get(self, container_id: str) -> _Container: ...


class DockerContainersClient(Protocol):
    """The slice of a ``docker.DockerClient`` the runner drives (structural)."""

    @property
    def containers(self) -> _Containers: ...


def _exit_code(container: _Container) -> int:
    state = container.attrs.get("State")
    if isinstance(state, Mapping):
        code = state.get("ExitCode")
        if isinstance(code, int):
            return code
    return 0


def _map_status(container: _Container | None) -> JobStatus:
    if container is None:
        return "not_found"
    live = _LIVE_STATES.get(container.status)
    if live is not None:
        return live
    # exited / dead — the exit code decides success vs failure (spec §3 terminal states).
    return "succeeded" if _exit_code(container) == 0 else "failed"


class DockerJobRunner:
    """``JobRunner`` backed by a single detached, run-once container."""

    def __init__(
        self,
        client: DockerContainersClient,
        *,
        image: str,
        nats_url: str | None = None,
        command: Sequence[str] = ("url4-cloud-runner",),
    ) -> None:
        self._client = client
        self._image = image
        self._nats_url = nats_url
        self._command = list(command)

    def schedule(self, topic: str, url4: str, deadline_s: int) -> str:
        name = job_name(topic)
        # WHY: the pre-check is the stateless single-use guard for the local adapter; races are
        # irrelevant on a single-daemon dev box (the atomic guard is k8s's create-conflict).
        if self.exists(topic):
            raise JobAlreadyExists(name)
        self._client.containers.run(
            self._image,
            name=name,
            command=self._command,
            environment=self._env(topic, url4, deadline_s),
            labels=RUNNER_LABELS,
            detach=True,
        )
        return name

    def stop(self, topic: str) -> None:
        container = self._get(topic)
        # INVARIANT: idempotent — an absent container is a successful stop.
        if container is not None:
            container.remove(force=True)

    def exists(self, topic: str) -> bool:
        return self._get(topic) is not None

    def status(self, topic: str) -> JobStatus:
        return _map_status(self._get(topic))

    def _get(self, topic: str) -> _Container | None:
        try:
            return self._client.containers.get(job_name(topic))
        except NotFound:
            return None

    def _env(self, topic: str, url4: str, deadline_s: int) -> dict[str, str]:
        env = {
            "URL4_CLOUD_TOPIC": topic,
            "URL4_CLOUD_EXPRESSION": url4,
            "URL4_CLOUD_JOB_DEADLINE_S": str(deadline_s),
        }
        if self._nats_url is not None:
            env["URL4_CLOUD_NATS_URL"] = self._nats_url
        return env
