from dataclasses import dataclass

import pytest
from _k8s_fakes import FakeCreatedJob, fake_created_job
from kubernetes.client import ApiException

from url4.streaming.interfaces import JobAlreadyExists, JobRunner, job_name
from url4_cloud import job_env
from url4_cloud.adapters.k8s import K8sJobRunner

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
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.states: dict[str, FakeJob] = {}
        self.deleted: list[str] = []

    def create_namespaced_job(self, namespace: str, body) -> FakeCreatedJob:
        name = body["metadata"]["name"]
        if name in self.jobs:
            raise ApiException(status=409)
        self.jobs[name] = body
        return fake_created_job(f"uid-{name}")

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


class FakeCoreV1Secrets:
    def __init__(self) -> None:
        self.secrets: dict[str, dict] = {}
        self.deleted: list[str] = []

    def create_namespaced_secret(self, namespace: str, body) -> dict:
        name = body["metadata"]["name"]
        self.secrets[name] = body
        return body

    def delete_namespaced_secret(self, name: str, namespace: str) -> dict:
        if name not in self.secrets:
            raise ApiException(status=404)
        del self.secrets[name]
        self.deleted.append(name)
        return {}


def _runner(client: FakeBatchV1, secrets_client: FakeCoreV1Secrets | None = None) -> K8sJobRunner:
    return K8sJobRunner(
        client,
        image="registry/url4-cloud:1",
        namespace="url4",
        env_configmap="url4-cloud-runner-env",
        secrets_client=secrets_client if secrets_client is not None else FakeCoreV1Secrets(),
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
    assert env[job_env.TOPIC] == TOPIC
    assert env[job_env.EXPRESSION] == "chat(hi)"
    # The NATS URL is deploy-time: the chart names and values it, the Job inherits it wholesale.
    assert container["envFrom"] == [{"configMapRef": {"name": "url4-cloud-runner-env"}}]


def _container_env_entries(client: FakeBatchV1, name: str) -> list[dict]:
    manifest = client.jobs[name]
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    return container["env"]


def _container_env(client: FakeBatchV1, name: str) -> dict[str, str]:
    return {e["name"]: e["value"] for e in _container_env_entries(client, name) if "value" in e}


def test_schedule_with_credential_and_profile_sets_env() -> None:
    client = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = _runner(client, secrets)
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=60, credential="tok", profile="p")

    env = _container_env(client, name)
    assert job_env.AIGATEWAY_TOKEN not in env
    assert env[job_env.AIGATEWAY_PROFILE] == "p"

    entries = {e["name"]: e for e in _container_env_entries(client, name)}
    token_ref = entries[job_env.AIGATEWAY_TOKEN]["valueFrom"]["secretKeyRef"]
    assert token_ref == {"name": f"{name}-cred", "key": "token"}
    assert secrets.secrets[f"{name}-cred"]["stringData"] == {"token": "tok"}
    owner_ref = secrets.secrets[f"{name}-cred"]["metadata"]["ownerReferences"][0]
    assert owner_ref["name"] == name
    assert owner_ref["uid"] == f"uid-{name}"


def test_schedule_without_credential_omits_aigateway_env() -> None:
    client = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = _runner(client, secrets)
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    env = _container_env(client, name)
    assert job_env.AIGATEWAY_TOKEN not in env
    assert job_env.AIGATEWAY_PROFILE not in env
    assert secrets.secrets == {}


def test_schedule_with_credential_but_no_secrets_client_fails_loud() -> None:
    client = FakeBatchV1()
    runner = K8sJobRunner(client, image="registry/url4-cloud:1", namespace="url4")

    with pytest.raises(RuntimeError, match="secrets_client"):
        runner.schedule(TOPIC, "chat(hi)", deadline_s=60, credential="tok")

    assert client.jobs == {}


def test_stop_deletes_the_credential_secret_alongside_the_job() -> None:
    client = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = _runner(client, secrets)
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=60, credential="tok")
    assert f"{name}-cred" in secrets.secrets

    runner.stop(TOPIC)

    assert f"{name}-cred" not in secrets.secrets
    assert client.deleted == [name]
    runner.stop(TOPIC)


def test_stop_without_a_forwarded_credential_never_touches_secrets() -> None:
    client = FakeBatchV1()
    secrets = FakeCoreV1Secrets()
    runner = _runner(client, secrets)
    runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    runner.stop(TOPIC)

    assert secrets.deleted == []


def test_secret_create_failure_deletes_the_just_created_job_and_reraises() -> None:
    class BoomSecrets(FakeCoreV1Secrets):
        def create_namespaced_secret(self, namespace: str, body) -> dict:
            raise ApiException(status=500)

    client = FakeBatchV1()
    runner = _runner(client, BoomSecrets())

    with pytest.raises(ApiException):
        runner.schedule(TOPIC, "chat(hi)", deadline_s=60, credential="tok")

    assert client.jobs == {}
    assert client.deleted == [job_name(TOPIC)]


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
    runner.stop(TOPIC)


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
        def create_namespaced_job(self, namespace: str, body) -> FakeCreatedJob:
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


def _pod(client: FakeBatchV1, name: str) -> dict:
    return client.jobs[name]["spec"]["template"]["spec"]


def test_runner_job_container_is_hardened_like_the_app() -> None:
    client = FakeBatchV1()
    name = _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    sec = _pod(client, name)["containers"][0]["securityContext"]
    assert sec["allowPrivilegeEscalation"] is False
    assert sec["capabilities"] == {"drop": ["ALL"]}
    assert sec["runAsNonRoot"] is True
    assert sec["runAsUser"] == 1000
    assert sec["readOnlyRootFilesystem"] is True


def test_runner_job_pod_sets_the_restricted_seccomp_profile() -> None:
    client = FakeBatchV1()
    name = _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert _pod(client, name)["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}


def test_runner_job_mounts_a_writable_tmp_for_the_read_only_root() -> None:
    client = FakeBatchV1()
    name = _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    pod = _pod(client, name)
    assert {"name": "tmp", "emptyDir": {}} in pod["volumes"]
    mounts = pod["containers"][0]["volumeMounts"]
    assert {"name": "tmp", "mountPath": "/tmp"} in mounts


def test_runner_job_does_not_mount_a_serviceaccount_token() -> None:
    client = FakeBatchV1()
    name = _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert _pod(client, name)["automountServiceAccountToken"] is False


def test_runner_job_carries_the_configured_resources() -> None:
    client = FakeBatchV1()
    runner = K8sJobRunner(
        client,
        image="registry/url4-cloud:1",
        namespace="url4",
        resources={"requests": {"cpu": "200m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}},
    )
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    container = _pod(client, name)["containers"][0]
    assert container["resources"] == {
        "requests": {"cpu": "200m", "memory": "256Mi"},
        "limits": {"memory": "1Gi"},
    }


def test_runner_job_omits_resources_when_unset() -> None:
    client = FakeBatchV1()
    name = _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert "resources" not in _pod(client, name)["containers"][0]


def test_runner_job_ttl_is_forwarded_so_finished_jobs_are_reclaimed() -> None:
    client = FakeBatchV1()
    runner = K8sJobRunner(client, image="registry/url4-cloud:1", namespace="url4", job_ttl_s=57660)
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert client.jobs[name]["spec"]["ttlSecondsAfterFinished"] == 57660


def test_runner_rejects_a_job_ttl_below_min_job_ttl_at_construction() -> None:
    with pytest.raises(ValueError, match="job_ttl_s=30 is below min_job_ttl_s=60"):
        K8sJobRunner(
            FakeBatchV1(),
            image="registry/url4-cloud:1",
            namespace="url4",
            job_ttl_s=30,
            min_job_ttl_s=60,
        )


def test_runner_accepts_a_job_ttl_at_or_above_min_job_ttl() -> None:
    client = FakeBatchV1()
    runner = K8sJobRunner(
        client,
        image="registry/url4-cloud:1",
        namespace="url4",
        job_ttl_s=60,
        min_job_ttl_s=60,
    )
    name = runner.schedule(TOPIC, "chat(hi)", deadline_s=60)
    assert client.jobs[name]["spec"]["ttlSecondsAfterFinished"] == 60


def test_runner_job_omits_ttl_when_unset_so_the_replay_guard_never_expires() -> None:
    client = FakeBatchV1()
    name = _runner(client).schedule(TOPIC, "chat(hi)", deadline_s=60)

    assert "ttlSecondsAfterFinished" not in client.jobs[name]["spec"]
