"""``K8sJobRunner`` — the ``JobRunner`` over a batch/v1 Job (run-once, 16 h cap; spec §9).

Run-once contract: ``backoffLimit: 0`` + ``restartPolicy: Never`` (retry = new token/new job,
spec §2.3), and ``activeDeadlineSeconds`` is the hard timeout that surfaces as ``timed_out``. The
``kubernetes.client.BatchV1Api`` is injected (structurally, :class:`BatchV1JobsClient`) so tests
drive a fake — no real cluster (INFRA rule).
"""

from collections.abc import Mapping, Sequence
from typing import Protocol

from kubernetes.client import ApiException

from url4_cloud.jobs.port import RUNNER_LABELS, JobAlreadyExists, JobStatus, job_name

_CONFLICT = 409
_NOT_FOUND = 404


class _JobCondition(Protocol):
    @property
    def type(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def reason(self) -> str | None: ...


class _JobStatusView(Protocol):
    @property
    def active(self) -> int | None: ...
    @property
    def conditions(self) -> Sequence[_JobCondition] | None: ...


class _JobView(Protocol):
    @property
    def status(self) -> _JobStatusView | None: ...


class BatchV1JobsClient(Protocol):
    """The slice of ``kubernetes.client.BatchV1Api`` the runner drives.

    Structural: the real client and the test fake both satisfy it. Reads return a ``_JobView``
    (the real ``V1Job`` and a fake both expose ``.status.active`` / ``.status.conditions``).
    """

    def create_namespaced_job(self, namespace: str, body: Mapping[str, object]) -> object: ...
    def read_namespaced_job(self, name: str, namespace: str) -> _JobView: ...
    def delete_namespaced_job(self, name: str, namespace: str) -> object: ...


def _terminal_status(conditions: Sequence[_JobCondition] | None) -> JobStatus | None:
    for cond in conditions or ():
        if cond.status != "True":
            continue
        if cond.type == "Complete":
            return "succeeded"
        if cond.type == "Failed":
            # WHY: k8s stamps reason ``DeadlineExceeded`` when activeDeadlineSeconds fires (§3).
            return "timed_out" if cond.reason == "DeadlineExceeded" else "failed"
    return None


def _map_status(job: _JobView | None) -> JobStatus:
    if job is None:
        return "not_found"
    view = job.status
    terminal = _terminal_status(view.conditions if view else None)
    if terminal is not None:
        return terminal
    return "running" if (view and view.active) else "scheduled"


class K8sJobRunner:
    """``JobRunner`` backed by a namespace-scoped batch/v1 Job."""

    def __init__(
        self,
        client: BatchV1JobsClient,
        *,
        image: str,
        namespace: str = "default",
        nats_url: str | None = None,
        command: Sequence[str] = ("url4-cloud-runner",),
    ) -> None:
        self._client = client
        self._image = image
        self._namespace = namespace
        self._nats_url = nats_url
        self._command = list(command)

    def schedule(self, topic: str, url4: str, deadline_s: int) -> str:
        name = job_name(topic)
        try:
            self._client.create_namespaced_job(
                self._namespace, self._manifest(name, topic, url4, deadline_s)
            )
        except ApiException as exc:
            if exc.status == _CONFLICT:
                raise JobAlreadyExists(name) from exc
            raise
        return name

    def stop(self, topic: str) -> None:
        try:
            self._client.delete_namespaced_job(job_name(topic), self._namespace)
        except ApiException as exc:
            # INVARIANT: idempotent — an absent job is a successful stop.
            if exc.status != _NOT_FOUND:
                raise

    def exists(self, topic: str) -> bool:
        return self._read(topic) is not None

    def status(self, topic: str) -> JobStatus:
        return _map_status(self._read(topic))

    def _read(self, topic: str) -> _JobView | None:
        try:
            return self._client.read_namespaced_job(job_name(topic), self._namespace)
        except ApiException as exc:
            if exc.status == _NOT_FOUND:
                return None
            raise

    def _env(self, topic: str, url4: str, deadline_s: int) -> list[dict[str, str]]:
        env = [
            {"name": "URL4_CLOUD_TOPIC", "value": topic},
            {"name": "URL4_CLOUD_EXPRESSION", "value": url4},
            {"name": "URL4_CLOUD_JOB_DEADLINE_S", "value": str(deadline_s)},
        ]
        if self._nats_url is not None:
            env.append({"name": "URL4_CLOUD_NATS_URL", "value": self._nats_url})
        return env

    def _manifest(self, name: str, topic: str, url4: str, deadline_s: int) -> dict[str, object]:
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": name, "labels": RUNNER_LABELS},
            "spec": {
                "backoffLimit": 0,
                "activeDeadlineSeconds": deadline_s,
                "template": {
                    "metadata": {"labels": RUNNER_LABELS},
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "runner",
                                "image": self._image,
                                "command": self._command,
                                "env": self._env(topic, url4, deadline_s),
                            }
                        ],
                    },
                },
            },
        }
