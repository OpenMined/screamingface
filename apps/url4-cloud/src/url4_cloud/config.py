"""Typed settings for the url4-cloud App, loaded from `URL4_CLOUD_*` environment variables."""

from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from url4_cloud import job_env

# WHY a margin at all: the App decides a token is expired from its own clock, while the k8s TTL
# controller deletes the Job from the control plane's. Without slack a skewed pair could reclaim
# the guard a few seconds before the token is actually refused. 60s is far beyond realistic
# in-cluster skew and still ~500x cheaper than the old job_deadline_s-based floor.
_TTL_SKEW_MARGIN_S = 60

RunnerBackend = Literal["none", "k8s"]
"""Which ``JobRunner`` substrate the deployed App schedules runs on (spec §9).

``k8s`` is prod (namespace-scoped batch/v1 Jobs) and ``none`` a stream-only App that mints tokens
and bridges NATS but schedules nothing.
"""

# WHY a named module constant (not a bare literal) for the insecure default: the prod guard in
# app.py (_require_prod_secret) compares against this same sentinel so the two never drift. If the
# default changes and the guard isn't updated, a prod boot would silently proceed on the weak
# secret.
INSECURE_DEFAULT_JWT_SECRET = "dev-insecure-change-me"

LOCAL_AIGATEWAY_BASE_URL = "http://127.0.0.1:9105"
"""The AI Gateway address local-mode connection operations fall back to.

WHY it lives beside `aigateway_base_url` rather than in `local.py`: it is a DEFAULT for that
setting, not a property of how local mode is assembled, and stating it here keeps the field and
its local fallback from drifting apart. An explicit `URL4_CLOUD_AIGATEWAY_BASE_URL` still wins —
`create_local_app` only substitutes this when the setting is unset.

INVARIANT: loopback, like `LOCAL_HOST`. Local mode is a single-process developer deployment, and
the gateway it manages credentials through is the one running beside it.
"""


class Settings(BaseSettings):
    """Environment-backed configuration for the App: auth, NATS, job-runner backend selection,
    and model-catalog cache tuning."""

    model_config = SettingsConfigDict(env_prefix="URL4_CLOUD_")

    # WHY: HS256 signing secret for the JWT topic-capability token (spec §4). Never logged.
    #
    # The prod guard in app.py rejects the insecure DEFAULT, but sentinel equality alone would
    # pass any short string — a 4-character production secret is brute-forceable and satisfied it.
    # RFC 7518 §3.2 requires an HMAC key at least as long as the hash output; below that, PyJWT
    # itself warns. Enforced here so a weak secret fails at startup rather than at the first
    # forged token.
    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    # WHY the shared constant and not a literal: `job_env` states the fallback beside the variable
    # name so serve and run cannot be pointed at different brokers by a one-sided edit.
    nats_url: str = job_env.DEFAULT_NATS_URL
    # INVARIANT: stateless iat window (seconds) — start rejected when now - iat exceeds it (§4).
    iat_window_s: int = 60
    # WHY: sync-hold cap; a run outliving it degrades to 202 async (spec §5).
    sync_max_wait_s: float = 30.0
    # WHY: idle interval between WS HeartbeatEvents for liveness (spec §6).
    ws_heartbeat_s: float = 15.0
    # INVARIANT: k8s Job activeDeadlineSeconds ceiling = 16h (spec §3).
    job_deadline_s: int = 57600
    # WHY: the run substrate is deployment-shaped, not code-shaped — the helm chart sets `k8s`.
    # Default `none` keeps a bare `Settings()` from reaching for a cluster.
    runner: RunnerBackend = "none"
    # INVARIANT: the App's RBAC Role is namespace-scoped, so Jobs are only ever created here (§9).
    namespace: str = "default"
    # WHY this is still a setting when the Job now runs the App's OWN image: a process cannot
    # reliably learn the image reference it was started from (the pod spec holds it, reading it
    # back needs RBAC on pods and the Downward API does not expose it), so the deployment states
    # it. The chart renders the same `image:` it gives the Deployment, which is what keeps the
    # two in lockstep. It is a distinct field rather than a hardcoded constant precisely so a
    # deployment CAN pin the Job to a different tag during a staged rollout.
    runner_image: str = "url4-cloud:latest"
    # WHY: the model catalog forwards the CALLER's credential to aigateway directly, and this is
    # its ONLY consumer (`catalog/__init__.py:build_catalog_service`) — despite sitting among the
    # runner-config fields around it, it is no longer forwarded into a Runner Job's env (that now
    # travels via `runner_env_configmap`/`K8sJobRunner._env_from`, below). It used to be: the
    # Runner's own fallback is loopback (127.0.0.1:9105), which inside a Job Pod resolves to
    # itself, not the aigateway Service — the trap `runner_env_configmap` now sidesteps by having
    # Helm value the variable directly instead of copying it through this field. `None` disables
    # the model-catalog endpoint (503 "not configured").
    aigateway_base_url: str | None = None
    # WHY: deploy-time Runner env travels as k8s objects the Job references with `envFrom`, so the
    # App neither names nor reads those variables — Helm owns name AND value. These two settings
    # are the only thing it needs: what to reference.
    runner_env_configmap: str | None = None
    # --- Tavily web tools (spec 2026-07-23). The connector declares web_search/web_fetch ONLY
    # when the Runner sees TAVILY_API_KEY; unset here => deny-by-default (dec:W5).
    #
    # WHY a reference (not a value): a ``batch/v1`` Job object is NOT a secret — readable with
    # ``get jobs`` RBAC (far looser than ``get secrets``) and surfaced in ``kubectl describe``/
    # ``-o yaml`` and the create-call audit log — so the key travels as a Secret *reference*, via
    # `envFrom.secretRef`, never a literal copied into the manifest (see
    # ``K8sJobRunner._env_from``). The name of the Secret the Runner Job's env references:
    tavily_secret_name: str | None = None
    # WHY: the Runner drives the url4 DAG engine and buffers model responses — it is the
    # workload that actually consumes CPU/memory here. Without requests it schedules into the
    # BestEffort QoS class (placed blind, evicted first, free to OOM its node), so the chart
    # supplies the numbers. Shape is the k8s `resources` block verbatim, e.g.
    # {"requests": {"cpu": "200m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}}.
    runner_resources: dict[str, dict[str, str]] | None = None
    # --- model catalog (OME-625). The catalog endpoint forwards the CALLER's credential, so
    # there is deliberately NO credential setting here: url4-cloud holds no aigateway secret.
    # `aigateway_base_url` above is the only precondition for the feature.
    #
    # WHY a TTL at all: the catalog is a provider registry — it changes on deploy, not on traffic.
    models_cache_ttl_s: float = 300.0
    # WHY a ceiling on stale service: an outage should not empty every client's model list, but an
    # indefinitely stale catalog would advertise models that may since have been retired.
    models_cache_stale_max_s: float = 3600.0
    # WHY: single-flight collapses CONCURRENT misses; this bounds SEQUENTIAL retries so a warm
    # caller polling through an aigateway outage does not hit upstream on every request.
    models_cache_error_backoff_s: float = 30.0
    # INVARIANT: cache keys derive from credentials url4-cloud does not verify, so the entry count
    # must be bounded rather than left to the caller population (spec §7).
    models_cache_max_entries: int = 256
    # INVARIANT: distinct credentials bypass single-flight entirely, so this bulkhead is the only
    # thing bounding concurrent upstream catalog fetches. The apigw is the rate limiter in front;
    # this is the in-app backstop.
    models_upstream_concurrency: int = 8

    # --- local mode (`url4-cloud serve --local`). Ignored by every other backend: these bound
    # resources that only a single-process deployment has to bound for itself.
    #
    # INVARIANT: local mode is selected by ARGV, never by these settings — they tune it, they do
    # not enable it. See the mode invariant in `cli.py`.
    #
    # WHY a concurrency cap at all: k8s spreads Jobs across a cluster and queues the surplus, but
    # every local run shares one event loop and one process, so admitting without bound degrades
    # the runs already in flight instead of delaying new ones.
    local_max_concurrent_runs: int = 8
    # WHY: the in-memory stream has no retention policy of its own (JetStream does), so a
    # long-lived dev server would accumulate every frame of every run it ever served.
    local_stream_max_frames: int = 10_000
    # WHY bounded run history: `status()` answers from finished tasks, so they are retained past
    # completion — this caps how many, the way `ttlSecondsAfterFinished` caps retained Jobs.
    local_max_run_history: int = 1000

    # INVARIANT: a finished Job's NAME is the stateless single-use replay guard, so reclaiming
    # it re-opens replay for that topic — but only for as long as the token is still usable.
    # See `effective_job_ttl_s` and `_reject_replayable_job_ttl`. None => derive the floor.
    job_ttl_s: int | None = None

    @property
    def effective_job_ttl_s(self) -> int:
        """Seconds a finished Runner Job is retained before k8s reclaims it.

        ``ttlSecondsAfterFinished`` counts from the moment the Job FINISHES, and the Job object
        exists for the whole run already — so the only gap the guard must cover is the interval
        after completion in which the starting token could still be presented again. A token
        carries ``exp = iat + iat_window_s`` (:meth:`JwtCodec.mint`), so it is rejected at auth,
        before ``exists()`` is ever consulted, once that window passes. ``iat_window_s`` is
        therefore the true floor; the extra :data:`_TTL_SKEW_MARGIN_S` only absorbs clock skew
        between the App validating ``exp`` and the k8s TTL controller doing the deletion.

        AIDEV-NOTE: this used to derive ``iat_window_s + job_deadline_s``, which conflated two
        different clocks — ``job_deadline_s`` measures a RUN, not the post-completion replay
        gap. At the 16 h default that retained ~960x more Job/Pod objects than the guard needs
        (~14 KB of etcd per request, held for 16 h), which is the scaling ceiling of this design
        rather than a property of it. Do not reintroduce the ``job_deadline_s`` term.
        """
        if self.job_ttl_s is not None:
            return self.job_ttl_s
        return self.iat_window_s + _TTL_SKEW_MARGIN_S

    @model_validator(mode="after")
    def _reject_replayable_job_ttl(self) -> Self:
        """INVARIANT: an explicit ``job_ttl_s`` may never drop below the token's own lifetime.

        Reclaiming the Job deletes the name that makes a replayed token fail with 409. Below
        ``iat_window_s`` that deletion can happen while the token is still within its ``exp``,
        opening a window for an already-spent token to start a second run. Raising it is
        legitimate (keeping failures around for post-mortem); dropping below the floor is a
        security regression, and is refused at startup rather than on the first replay.
        """
        if self.job_ttl_s is not None and self.job_ttl_s < self.iat_window_s:
            raise ValueError(
                f"job_ttl_s={self.job_ttl_s} is below the replay floor {self.iat_window_s} "
                f"(iat_window_s, the token's own lifetime) — a Job reclaimed while its token is "
                f"still valid re-opens replay"
            )
        return self
