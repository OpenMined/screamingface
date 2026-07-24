"""``K8sJobRunner`` — the ``JobRunner`` over a batch/v1 Job (run-once, 16 h cap; spec §9).

Run-once contract: ``backoffLimit: 0`` + ``restartPolicy: Never`` (retry = new token/new job,
spec §2.3), and ``activeDeadlineSeconds`` is the hard timeout that surfaces as ``timed_out``. The
``kubernetes.client.BatchV1Api`` is injected (structurally, :class:`BatchV1JobsClient`) so tests
drive a fake — no real cluster (INFRA rule).
"""

import contextlib
from collections.abc import Mapping, Sequence
from typing import Protocol

from kubernetes.client import ApiException

from url4_cloud.jobs.port import RUNNER_LABELS, JobAlreadyExists, JobStatus, job_name
from url4_cloud_runner.trace import parse_traceparent

_CONFLICT = 409
_NOT_FOUND = 404

# The key inside the per-run credential Secret's `stringData` — mirrors the Tavily convention
# (`tavily_secret_key`) of a single well-known key per Secret.
_CREDENTIAL_SECRET_KEY = "token"


def _credential_secret_name(job_name_: str) -> str:
    """The per-run Secret name for a Job's forwarded aigateway credential.

    Deterministic and derived from the (already deterministic) Job name, same shape as
    :func:`~url4_cloud.jobs.port.job_name` — both a fresh DNS-1123 label and, on retry-under-a-
    already-scheduled-topic, the same conflict the Job creation itself would already reject.
    """
    return f"{job_name_}-cred"


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


class _CreatedObjectMeta(Protocol):
    @property
    def uid(self) -> str: ...


class _CreatedJob(Protocol):
    @property
    def metadata(self) -> _CreatedObjectMeta: ...


class BatchV1JobsClient(Protocol):
    """The slice of ``kubernetes.client.BatchV1Api`` the runner drives.

    Structural: the real client and the test fake both satisfy it. Reads return a ``_JobView``
    (the real ``V1Job`` and a fake both expose ``.status.active`` / ``.status.conditions``).
    ``create_namespaced_job`` returns a ``_CreatedJob`` so its ``metadata.uid`` can seed the
    credential Secret's ``ownerReference`` (see :class:`CoreV1SecretsClient`).
    """

    def create_namespaced_job(self, namespace: str, body: Mapping[str, object]) -> _CreatedJob: ...
    def read_namespaced_job(self, name: str, namespace: str) -> _JobView: ...
    def delete_namespaced_job(self, name: str, namespace: str) -> object: ...


class CoreV1SecretsClient(Protocol):
    """The slice of ``kubernetes.client.CoreV1Api`` the runner drives for the per-run
    credential Secret it creates itself (never for the pre-provisioned, operator-managed
    Tavily one referenced via ``tavily_secret_ref``)."""

    def create_namespaced_secret(self, namespace: str, body: Mapping[str, object]) -> object: ...
    def delete_namespaced_secret(self, name: str, namespace: str) -> object: ...


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
        aigateway_base_url: str | None = None,
        tavily_secret_ref: tuple[str, str] | None = None,
        resources: Mapping[str, Mapping[str, str]] | None = None,
        job_ttl_s: int | None = None,
        min_job_ttl_s: int | None = None,
        secrets_client: CoreV1SecretsClient | None = None,
    ) -> None:
        self._client = client
        # WHY required only when a run actually forwards a credential: the App's RBAC needs
        # `create`/`delete` on `secrets` for this (unlike the Tavily ref, which needs no secrets
        # RBAC at all — see `_env`). `schedule()` raises loudly on first use if a credential
        # arrives with no client wired, rather than falling back to the plaintext env this
        # exists to prevent.
        self._secrets_client = secrets_client
        self._image = image
        self._namespace = namespace
        self._nats_url = nats_url
        self._command = list(command)
        self._aigateway_base_url = aigateway_base_url
        # (secret name, key) for the Tavily web-tools credential; None => web tools stay off.
        self._tavily_secret_ref = tavily_secret_ref
        # WHY: the Runner is the workload that actually burns CPU/memory (it drives the url4 DAG
        # engine and buffers model responses). With no requests it lands in the BestEffort QoS
        # class — scheduled blind, evicted first, and free to OOM the node it shares. Passed
        # through verbatim so the chart owns the numbers.
        self._resources = resources
        # INVARIANT: the deterministic Job NAME is the stateless single-use replay guard (a 409
        # on create is what rejects a replayed token). Deleting a finished Job therefore re-opens
        # replay for that topic, so the TTL is not a free cleanup knob: it must outlive any token
        # that could still be presented — which is the TOKEN's lifetime, not the run's, because
        # the TTL clock starts at completion. `Settings._reject_replayable_job_ttl` enforces this
        # floor for the normal `factory.build_job_runner` composition path; `min_job_ttl_s` below
        # is this class's OWN defense of the same invariant, so a caller constructing
        # `K8sJobRunner` directly (bypassing `Settings`) cannot silently reopen the replay window.
        if job_ttl_s is not None and min_job_ttl_s is not None and job_ttl_s < min_job_ttl_s:
            raise ValueError(
                f"job_ttl_s={job_ttl_s} is below min_job_ttl_s={min_job_ttl_s} (the token's own "
                f"lifetime) — a Job reclaimed while its token is still valid re-opens replay"
            )
        self._job_ttl_s = job_ttl_s

    def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> str:
        if credential and self._secrets_client is None:
            # Fail loud rather than silently fall back to a plaintext env value — the whole
            # point of this branch is that a Job spec is not a secret store (see `_env`).
            raise RuntimeError(
                "K8sJobRunner received a credential to forward but no secrets_client was "
                "configured — refusing to inject it as a plaintext Job env value"
            )
        name = job_name(topic)
        try:
            created = self._client.create_namespaced_job(
                self._namespace,
                self._manifest(name, topic, url4, deadline_s, traceparent, credential, profile),
            )
        except ApiException as exc:
            if exc.status == _CONFLICT:
                raise JobAlreadyExists(name) from exc
            raise
        if credential:
            try:
                self._create_credential_secret(name, created, credential)
            except ApiException:
                # The Job now exists but its credential Secret does not — left alone, the Pod
                # would sit in CreateContainerConfigError until activeDeadlineSeconds eventually
                # times it out. Fail loud now instead: best-effort delete the Job we just
                # created (idempotent stop semantics) and re-raise the real failure.
                with contextlib.suppress(ApiException):
                    self._client.delete_namespaced_job(name, self._namespace)
                raise
        return name

    def _create_credential_secret(
        self, job_name_: str, created_job: _CreatedJob, credential: str
    ) -> None:
        assert self._secrets_client is not None  # guarded by schedule()'s precondition check
        self._secrets_client.create_namespaced_secret(
            self._namespace,
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "type": "Opaque",
                "metadata": {
                    "name": _credential_secret_name(job_name_),
                    "labels": RUNNER_LABELS,
                    # WHY an ownerReference to the Job: once the Job is reclaimed (explicit
                    # `stop()`, or `ttlSecondsAfterFinished` firing), the k8s garbage collector
                    # cascades the delete to this Secret too — a safety net alongside the
                    # explicit delete in `stop()` below, so a crash between the two never
                    # leaves a forwarded credential orphaned in etcd indefinitely.
                    "ownerReferences": [
                        {
                            "apiVersion": "batch/v1",
                            "kind": "Job",
                            "name": job_name_,
                            "uid": created_job.metadata.uid,
                            "controller": True,
                            "blockOwnerDeletion": True,
                        }
                    ],
                },
                "stringData": {_CREDENTIAL_SECRET_KEY: credential},
            },
        )

    def stop(self, topic: str) -> None:
        name = job_name(topic)
        if self._secrets_client is not None:
            try:
                self._secrets_client.delete_namespaced_secret(
                    _credential_secret_name(name), self._namespace
                )
            except ApiException as exc:
                # INVARIANT: idempotent — an absent/never-created secret is a no-op (a run with
                # no forwarded credential never had one).
                if exc.status != _NOT_FOUND:
                    raise
        try:
            self._client.delete_namespaced_job(name, self._namespace)
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

    def _env(
        self,
        name: str,
        topic: str,
        url4: str,
        deadline_s: int,
        traceparent: str | None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> list[dict[str, object]]:
        # WHY `object` values: most entries are plain `{"name","value"}` strings, but the Tavily
        # entry is a nested `valueFrom.secretKeyRef` mapping (see below) — the widened type is
        # what lets one env list carry both shapes.
        env: list[dict[str, object]] = [
            {"name": "URL4_CLOUD_TOPIC", "value": topic},
            {"name": "URL4_CLOUD_EXPRESSION", "value": url4},
            {"name": "URL4_CLOUD_JOB_DEADLINE_S", "value": str(deadline_s)},
        ]
        if self._nats_url is not None:
            env.append({"name": "URL4_CLOUD_NATS_URL", "value": self._nats_url})
        # WHY: the Runner's fallback is loopback, which in a Job Pod is the Pod itself — the
        # aigateway Service URL is deployment config and must travel with the Job (spec §9).
        if self._aigateway_base_url is not None:
            env.append({"name": "AIGATEWAY_BASE_URL", "value": self._aigateway_base_url})
        if traceparent is not None and parse_traceparent(traceparent) is not None:
            env.append({"name": "URL4_CLOUD_TRACEPARENT", "value": traceparent})
        # SECURITY: forwarded as a REFERENCE, never a literal — same rationale as the Tavily
        # entry below: a Job object is not a secret (readable with `get jobs` RBAC alone, echoed
        # by `kubectl describe`/`-o yaml` and the create-call audit log), so a literal here would
        # spray this per-run aigateway/CF Access credential across etcd in plaintext, one Job per
        # run. `schedule()` creates `_credential_secret_name(name)` (via
        # `_create_credential_secret`, AFTER the Job so its ownerReference has a real uid) before
        # this Pod is ever scheduled.
        if credential:
            env.append(
                {
                    "name": "AIGATEWAY_TOKEN",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": _credential_secret_name(name),
                            "key": _CREDENTIAL_SECRET_KEY,
                        }
                    },
                }
            )
        if profile is not None:
            env.append({"name": "AIGATEWAY_PROFILE", "value": profile})
        # INVARIANT: the Tavily key is forwarded as a REFERENCE, never a literal. A Job object is
        # not a secret (readable with `get jobs`, echoed by `kubectl describe`/`-o yaml` and the
        # create-call audit log), so copying this long-lived operator credential in would spray
        # plaintext across etcd, one Job per run. The kubelet resolves the ref at pod start;
        # `optional` stays false (the default) so a missing/misnamed Secret fails loud rather
        # than silently disabling web tools. `Settings` rejects the literal-on-k8s combination.
        if self._tavily_secret_ref is not None:
            name_, key_ = self._tavily_secret_ref
            env.append(
                {
                    "name": "TAVILY_API_KEY",
                    "valueFrom": {"secretKeyRef": {"name": name_, "key": key_}},
                }
            )
        return env

    def _manifest(
        self,
        name: str,
        topic: str,
        url4: str,
        deadline_s: int,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> dict[str, object]:
        container: dict[str, object] = {
            "name": "runner",
            "image": self._image,
            "command": self._command,
            "env": self._env(name, topic, url4, deadline_s, traceparent, credential, profile),
            # INVARIANT: at least as hardened as the App (deployment.yaml). The Runner evaluates
            # user-supplied url4 expressions and makes outbound calls, so it is the higher-risk
            # of the two workloads — it must never be the softer one. uid 1000 is the image's
            # own USER (Dockerfile), so this asserts rather than changes the runtime identity.
            "securityContext": {
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "runAsNonRoot": True,
                "runAsUser": 1000,
                "readOnlyRootFilesystem": True,
            },
            # WHY: the read-only root above needs one writable path, or any transitive dependency
            # that writes a temp file or cache crashes the Runner at an arbitrary later moment.
            "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
        }
        if self._resources is not None:
            container["resources"] = {k: dict(v) for k, v in self._resources.items()}
        spec: dict[str, object] = {
            "backoffLimit": 0,
            "activeDeadlineSeconds": deadline_s,
            "template": {
                "metadata": {"labels": RUNNER_LABELS},
                "spec": {
                    "restartPolicy": "Never",
                    # INVARIANT: no kubelet Service-link env. It would export
                    # `URL4_CLOUD_PORT=tcp://<ip>:<port>` for the App's own Service, colliding
                    # with this project's `URL4_CLOUD_` settings prefix. A Runner is configured
                    # ONLY by the env below.
                    "enableServiceLinks": False,
                    # Least privilege: the Runner never calls the k8s API (the App is the only
                    # API caller), so it has no use for a mounted ServiceAccount token.
                    "automountServiceAccountToken": False,
                    "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [container],
                    "volumes": [{"name": "tmp", "emptyDir": {}}],
                },
            },
        }
        if self._job_ttl_s is not None:
            spec["ttlSecondsAfterFinished"] = self._job_ttl_s
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": name, "labels": RUNNER_LABELS},
            "spec": spec,
        }
