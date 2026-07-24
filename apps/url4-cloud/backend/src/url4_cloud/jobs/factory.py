"""Composition root for the ``JobRunner`` port — selects the substrate adapter from env (§9).

FEATURE: a deployed App schedules Runner Jobs. ``create_app`` stays purely dependency-injected
(tests hand it fakes); this module is the ONE place that turns ``URL4_CLOUD_RUNNER`` into a real
adapter, so prod (helm/k8s) and bus-only profiles share a single wiring path instead of each
deployment growing its own glue.

AIDEV-NOTE: the substrate clients are constructed through injected factories so this module is
testable headless — importing it must never touch a kube-config (INFRA rule).
"""

from collections.abc import Callable
from typing import cast

from url4_cloud.config import Settings
from url4_cloud.jobs.k8s import BatchV1JobsClient, CoreV1SecretsClient, K8sJobRunner
from url4_cloud.jobs.port import JobRunner

# INVARIANT: the Runner is its own image now (apps/url4-cloud/runner/Dockerfile), entered
# through its own console script (spec §9) — the backend schedules it as a batch/v1 Job and
# never runs it in-process in prod (only local-dev mode does, via the in-process runner).
RUNNER_COMMAND = ("url4-cloud-runner",)


def _in_cluster_batch_client() -> BatchV1JobsClient:  # pragma: no cover - live cluster (INFRA)
    """Build a ``BatchV1Api`` from the ServiceAccount the chart mounts.

    WHY lazy import: ``kubernetes.config`` reads the in-cluster token at call time; keeping it
    out of module scope means importing ``url4_cloud`` never requires a cluster.

    WHY cast: ``kubernetes``' generated client is loosely typed (``**kwargs``-shaped returns), so
    it cannot be *proven* to satisfy the narrow :class:`BatchV1JobsClient` slice the adapter drives
    — the adapter's own unit tests pin the three calls that actually matter.
    """
    from kubernetes.client import BatchV1Api
    from kubernetes.config import load_incluster_config

    load_incluster_config()
    return cast(BatchV1JobsClient, BatchV1Api())


def _in_cluster_secrets_client() -> CoreV1SecretsClient:  # pragma: no cover - live cluster (INFRA)
    """Build a ``CoreV1Api`` from the ServiceAccount the chart mounts — the per-run credential
    Secret's client (see :meth:`K8sJobRunner._create_credential_secret`). Same lazy-import/cast
    rationale as :func:`_in_cluster_batch_client`."""
    from kubernetes.client import CoreV1Api
    from kubernetes.config import load_incluster_config

    load_incluster_config()
    return cast(CoreV1SecretsClient, CoreV1Api())


def build_job_runner(
    settings: Settings,
    *,
    k8s_client_factory: Callable[[], BatchV1JobsClient] = _in_cluster_batch_client,
    k8s_secrets_client_factory: Callable[[], CoreV1SecretsClient] = _in_cluster_secrets_client,
) -> JobRunner | None:
    """Return the ``JobRunner`` for ``settings.runner`` — or ``None`` for the bus-only profile.

    INVARIANT: total over :data:`~url4_cloud.config.RunnerBackend`. An unknown value can never
    reach here — ``Settings`` rejects it at construction, so misconfiguration fails at startup
    rather than on the first ``GET /?q=``.
    """
    if settings.runner == "k8s":
        # WHY only the (name, key) pair: the App forwards a Secret REFERENCE into the Job and
        # never reads the Tavily credential itself — so it needs no `get secrets` RBAC, and
        # rotating the Secret takes effect on the next Job without restarting the App.
        tavily_ref = (
            (settings.tavily_secret_name, settings.tavily_secret_key)
            if settings.tavily_secret_name
            else None
        )
        return K8sJobRunner(
            k8s_client_factory(),
            image=settings.runner_image,
            namespace=settings.namespace,
            nats_url=settings.nats_url,
            command=RUNNER_COMMAND,
            aigateway_base_url=settings.aigateway_base_url,
            tavily_secret_ref=tavily_ref,
            resources=settings.runner_resources,
            job_ttl_s=settings.effective_job_ttl_s,
            min_job_ttl_s=settings.iat_window_s,
            secrets_client=k8s_secrets_client_factory(),
        )
    return None
