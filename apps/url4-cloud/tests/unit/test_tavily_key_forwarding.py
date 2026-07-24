"""The App plumbs the Tavily web-tools key into every Runner Job (web tools, spec 2026-07-23).

FEATURE: the aigateway connector declares ``web_search``/``web_fetch`` and runs its bounded
tool-calling loop ONLY when the Runner sees ``TAVILY_API_KEY``
(``url4_cloud_runner.__main__.build_executor``). Without this forwarding the connector's web
tools are unreachable in every deployed configuration — ``web_tools_enabled`` is structurally
always ``False``.

INVARIANT (the security core of this unit): the App forwards a *reference*
(``valueFrom.secretKeyRef``), NEVER the literal key. A ``batch/v1`` Job object is not a secret
— it is readable with ``get jobs`` RBAC (far looser than ``get secrets``) and shows up in
``kubectl describe``/``-o yaml`` and create-call audit logs. Copying a long-lived operator
API key into one Job spec per run would spray plaintext across etcd.
"""

from typing import Any

from _k8s_fakes import FakeCreatedJob, fake_created_job

from url4_cloud.config import Settings
from url4_cloud.jobs.factory import build_job_runner
from url4_cloud.jobs.k8s import K8sJobRunner


class _RecordingBatchApi:
    """Captures the Job manifest the adapter would POST."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_namespaced_job(self, namespace: str, body: Any) -> FakeCreatedJob:
        self.created.append(dict(body))
        return fake_created_job(f"uid-{body['metadata']['name']}")

    def read_namespaced_job(self, name: str, namespace: str) -> Any:  # pragma: no cover
        raise NotImplementedError

    def delete_namespaced_job(self, name: str, namespace: str) -> object:  # pragma: no cover
        raise NotImplementedError


class _RecordingSecretsApi:
    """Captures the per-run credential Secret the adapter would POST — the ``CoreV1SecretsClient``
    counterpart to :class:`_RecordingBatchApi`."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_namespaced_secret(self, namespace: str, body: Any) -> object:
        self.created.append(dict(body))
        return object()

    def delete_namespaced_secret(self, name: str, namespace: str) -> object:  # pragma: no cover
        raise NotImplementedError


def _job_env(api: _RecordingBatchApi) -> list[dict[str, Any]]:
    spec = api.created[0]["spec"]
    container = spec["template"]["spec"]["containers"][0]  # type: ignore[index]
    return container["env"]  # type: ignore[index,no-any-return]


def _entry(env: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((e for e in env if e["name"] == name), None)


# --- k8s: reference-pass -----------------------------------------------------------------


def test_k8s_job_env_carries_a_secret_ref_not_the_literal_key() -> None:
    # INVARIANT: the Job spec names the Secret; the plaintext never enters the manifest.
    api = _RecordingBatchApi()
    runner = K8sJobRunner(
        api, image="url4-cloud:kind", tavily_secret_ref=("url4-cloud-tavily", "api-key")
    )

    runner.schedule("topic-a", "(x)!go", 60)

    entry = _entry(_job_env(api), "TAVILY_API_KEY")
    assert entry is not None
    assert entry["valueFrom"]["secretKeyRef"] == {
        "name": "url4-cloud-tavily",
        "key": "api-key",
    }
    # INVARIANT: no `value` key at all — a literal would defeat the whole point.
    assert "value" not in entry


def test_k8s_job_env_omits_tavily_when_no_secret_ref_is_configured() -> None:
    # INVARIANT: deny-by-default (dec:W5) — unconfigured means the Runner never sees the var,
    # so the connector's request body stays byte-identical to the no-web-tools shape.
    api = _RecordingBatchApi()
    runner = K8sJobRunner(api, image="url4-cloud:kind")

    runner.schedule("topic-b", "(x)!go", 60)

    assert _entry(_job_env(api), "TAVILY_API_KEY") is None


def test_k8s_tavily_secret_ref_does_not_disturb_the_other_job_env() -> None:
    # WHY: the ref is additive; the pre-existing carriage (topic/expression/aigateway) is a
    # contract other tests pin, and this unit must not perturb it.
    api = _RecordingBatchApi()
    runner = K8sJobRunner(
        api,
        image="url4-cloud:kind",
        aigateway_base_url="http://aigateway:9105",
        tavily_secret_ref=("s", "k"),
        secrets_client=_RecordingSecretsApi(),
    )

    runner.schedule("topic-c", "(x)!go", 60, credential="cred-1")

    env = _job_env(api)
    assert _entry(env, "URL4_CLOUD_TOPIC") == {"name": "URL4_CLOUD_TOPIC", "value": "topic-c"}
    assert _entry(env, "AIGATEWAY_BASE_URL") == {
        "name": "AIGATEWAY_BASE_URL",
        "value": "http://aigateway:9105",
    }
    # INVARIANT: the forwarded aigateway credential is a Secret REFERENCE too — same rationale
    # as the Tavily key above — never a literal Job env value.
    token_entry = _entry(env, "AIGATEWAY_TOKEN")
    assert token_entry is not None
    assert "value" not in token_entry
    assert token_entry["valueFrom"]["secretKeyRef"]["key"] == "token"


# --- Settings + factory wiring -----------------------------------------------------------


def test_k8s_settings_build_a_runner_carrying_the_secret_ref() -> None:
    settings = Settings(
        runner="k8s",
        tavily_secret_name="url4-cloud-tavily",
        tavily_secret_key="api-key",
    )

    runner = build_job_runner(
        settings,
        k8s_client_factory=_RecordingBatchApi,
        k8s_secrets_client_factory=_RecordingSecretsApi,
    )

    assert isinstance(runner, K8sJobRunner)
    assert runner._tavily_secret_ref == ("url4-cloud-tavily", "api-key")


def test_k8s_settings_without_a_secret_name_leave_the_ref_unset() -> None:
    runner = build_job_runner(
        Settings(runner="k8s"),
        k8s_client_factory=_RecordingBatchApi,
        k8s_secrets_client_factory=_RecordingSecretsApi,
    )

    assert isinstance(runner, K8sJobRunner)
    assert runner._tavily_secret_ref is None
