"""K8sJobRunner against a fake BatchV1Api — no real cluster (INFRA rule)."""

from dataclasses import dataclass

import pytest
from kubernetes.client import ApiException

from url4_cloud.jobs import JobAlreadyExists, JobRunner, K8sJobRunner, job_name

TOPIC = "cap-topic"


@dataclass
class FakeCondition:
    type: str
    status: str
    reason: str | None = None


@dataclass
class FakeJobStatus:
    active: int | None = None
    conditions: list[FakeCondition] | None = None


@dataclass
class FakeJob:
    status: FakeJobStatus | None = None


class FakeBatchV1:
    """Records created Job manifests; raises ApiException like the real BatchV1Api."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.states: dict[str, FakeJob] = {}
        self.deleted: list[str] = []

    def create_namespaced_job(self, namespace: str, body) -> dict:
        name = body["metadata"]["name"]
        if name in self.jobs:
            raise ApiException(status=409)
        self.jobs[name] = body
        return body

    def read_namespaced_job(self, name: str, namespace: str) -> FakeJob:
        if name not in self.jobs:
            raise ApiException(status=404)
        return self.states.get(name, FakeJob())

    def delete_namespaced_job(self, name: str, namespace: str) -> dict:
        if name not in self.jobs:
            raise ApiException(status=404)
        del self.jobs[name]
        self.deleted.append(name)
        return {}


def _runner(client: FakeBatchV1) -> K8sJobRunner:
    return K8sJobRunner(
        client, image="registry/url4-cloud:1", namespace="url4", nats_url="nats://n:4222"
    )


def test_runner_satisfies_the_port() -> None:
    runner: JobRunner = _runner(FakeBatchV1())
    assert isinstance(runner, JobRunner)


def test_schedule_builds_a_run_once_named_spec() -> None:
    client = FakeBatchV1()
    runner = _runner(client)
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=57600)

    assert name == job_name(TOPIC)
    manifest = client.jobs[name]
    assert manifest["metadata"]["name"] == name
    spec = manifest["spec"]
    assert spec["backoffLimit"] == 0
    assert spec["activeDeadlineSeconds"] == 57600
    pod = spec["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    container = pod["containers"][0]
    assert container["image"] == "registry/url4-cloud:1"
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["URL4_CLOUD_TOPIC"] == TOPIC
    assert env["URL4_CLOUD_EXPRESSION"] == "chat(hi)"
    assert env["URL4_CLOUD_NATS_URL"] == "nats://n:4222"


def test_schedule_twice_is_the_stateless_single_use_guard() -> None:
    client = FakeBatchV1()
    runner = _runner(client)
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    with pytest.raises(JobAlreadyExists):
        runner.schedule(TOPIC, "chat(hi)", deadline_s=60)


def test_exists_reflects_the_scheduled_job() -> None:
    client = FakeBatchV1()
    runner = _runner(client)
    assert runner.exists(TOPIC) is False
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    assert runner.exists(TOPIC) is True


def test_stop_deletes_the_job_and_is_idempotent() -> None:
    client = FakeBatchV1()
    runner = _runner(client)
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    runner.stop(TOPIC)
    assert client.deleted == [job_name(TOPIC)]
    assert runner.exists(TOPIC) is False
    runner.stop(TOPIC)  # already gone — no error


def _schedule_with_state(state: FakeJobStatus | None) -> K8sJobRunner:
    client = FakeBatchV1()
    runner = _runner(client)
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    if state is not None:
        client.states[job_name(TOPIC)] = FakeJob(status=state)
    return runner


def test_status_not_found_for_unknown_topic() -> None:
    runner = _runner(FakeBatchV1())
    assert runner.status(TOPIC) == "not_found"


def test_status_scheduled_when_no_status_yet() -> None:
    runner = _schedule_with_state(None)
    assert runner.status(TOPIC) == "scheduled"


def test_status_running_when_active() -> None:
    runner = _schedule_with_state(FakeJobStatus(active=1))
    assert runner.status(TOPIC) == "running"


def test_status_succeeded_on_complete_condition() -> None:
    runner = _schedule_with_state(
        FakeJobStatus(conditions=[FakeCondition(type="Complete", status="True")])
    )
    assert runner.status(TOPIC) == "succeeded"


def test_status_failed_on_failed_condition() -> None:
    runner = _schedule_with_state(
        FakeJobStatus(
            conditions=[FakeCondition(type="Failed", status="True", reason="BackoffLimitExceeded")]
        )
    )
    assert runner.status(TOPIC) == "failed"


def test_status_timed_out_on_deadline_exceeded() -> None:
    runner = _schedule_with_state(
        FakeJobStatus(
            conditions=[FakeCondition(type="Failed", status="True", reason="DeadlineExceeded")]
        )
    )
    assert runner.status(TOPIC) == "timed_out"


def test_status_ignores_a_false_condition() -> None:
    runner = _schedule_with_state(
        FakeJobStatus(active=1, conditions=[FakeCondition(type="Complete", status="False")])
    )
    assert runner.status(TOPIC) == "running"


def test_status_reraises_non_404_api_errors() -> None:
    class Boom(FakeBatchV1):
        def read_namespaced_job(self, name: str, namespace: str) -> FakeJob:
            raise ApiException(status=500)

    runner = _runner(Boom())
    with pytest.raises(ApiException):
        runner.status(TOPIC)


def test_schedule_reraises_non_409_api_errors() -> None:
    class Boom(FakeBatchV1):
        def create_namespaced_job(self, namespace: str, body) -> dict:
            raise ApiException(status=500)

    runner = _runner(Boom())
    with pytest.raises(ApiException):
        runner.schedule(TOPIC, "chat(hi)", deadline_s=60)


def test_stop_reraises_non_404_api_errors() -> None:
    class Boom(FakeBatchV1):
        def delete_namespaced_job(self, name: str, namespace: str) -> dict:
            raise ApiException(status=500)

    runner = _runner(Boom())
    with pytest.raises(ApiException):
        runner.stop(TOPIC)
