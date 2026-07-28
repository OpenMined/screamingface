"""DockerJobRunner against a fake docker client — no real daemon (INFRA rule)."""

from dataclasses import dataclass, field

import pytest
from docker.errors import NotFound

from url4_cloud.jobs import DockerJobRunner, JobAlreadyExists, JobRunner, job_name

TOPIC = "cap-topic"


@dataclass
class FakeContainer:
    name: str
    status: str = "created"
    attrs: dict = field(default_factory=dict)
    removed: bool = False
    run_kwargs: dict = field(default_factory=dict)

    def remove(self, force: bool = False) -> None:
        self.removed = True


class FakeContainers:
    def __init__(self) -> None:
        self.store: dict[str, FakeContainer] = {}
        self.runs: list[dict] = []

    def run(self, image: str, **kwargs: object) -> FakeContainer:
        name = str(kwargs["name"])
        container = FakeContainer(name=name, run_kwargs={"image": image, **kwargs})
        self.store[name] = container
        self.runs.append({"image": image, **kwargs})
        return container

    def get(self, container_id: str) -> FakeContainer:
        container = self.store.get(container_id)
        if container is None or container.removed:
            raise NotFound(f"no such container: {container_id}")
        return container


class FakeDocker:
    def __init__(self) -> None:
        self.containers = FakeContainers()


def _runner(client: FakeDocker) -> DockerJobRunner:
    return DockerJobRunner(client, image="registry/url4-cloud:1", nats_url="nats://n:4222")


def test_runner_satisfies_the_port() -> None:
    runner: JobRunner = _runner(FakeDocker())
    assert isinstance(runner, JobRunner)


def test_schedule_runs_a_named_detached_container() -> None:
    client = FakeDocker()
    runner = _runner(client)
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=57600)

    assert name == job_name(TOPIC)
    run = client.containers.runs[0]
    assert run["name"] == name
    assert run["image"] == "registry/url4-cloud:1"
    assert run["detach"] is True
    env = run["environment"]
    assert env["URL4_CLOUD_TOPIC"] == TOPIC
    assert env["URL4_CLOUD_EXPRESSION"] == "chat(hi)"
    assert env["URL4_CLOUD_NATS_URL"] == "nats://n:4222"


def test_schedule_twice_is_the_stateless_single_use_guard() -> None:
    runner = _runner(FakeDocker())
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    with pytest.raises(JobAlreadyExists):
        runner.schedule(TOPIC, "chat(hi)", deadline_s=60)


def test_exists_reflects_the_running_container() -> None:
    runner = _runner(FakeDocker())
    assert runner.exists(TOPIC) is False
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    assert runner.exists(TOPIC) is True


def test_stop_removes_the_container_and_is_idempotent() -> None:
    client = FakeDocker()
    runner = _runner(client)
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    runner.stop(TOPIC)
    assert client.containers.store[job_name(TOPIC)].removed is True
    assert runner.exists(TOPIC) is False
    runner.stop(TOPIC)  # already removed — no error


def _schedule_then_set(status: str, attrs: dict | None = None) -> DockerJobRunner:
    client = FakeDocker()
    runner = _runner(client)
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    container = client.containers.store[job_name(TOPIC)]
    container.status = status
    container.attrs = attrs or {}
    return runner


def test_status_not_found_for_unknown_topic() -> None:
    runner = _runner(FakeDocker())
    assert runner.status(TOPIC) == "not_found"


def test_status_scheduled_when_created() -> None:
    assert _schedule_then_set("created").status(TOPIC) == "scheduled"


def test_status_running() -> None:
    assert _schedule_then_set("running").status(TOPIC) == "running"


def test_status_succeeded_on_zero_exit() -> None:
    runner = _schedule_then_set("exited", {"State": {"ExitCode": 0}})
    assert runner.status(TOPIC) == "succeeded"


def test_status_failed_on_nonzero_exit() -> None:
    runner = _schedule_then_set("exited", {"State": {"ExitCode": 1}})
    assert runner.status(TOPIC) == "failed"


def test_status_succeeded_when_exit_state_missing() -> None:
    # exited with no State block → exit code defaults to 0 (the defensive fallback path).
    assert _schedule_then_set("exited", {}).status(TOPIC) == "succeeded"
