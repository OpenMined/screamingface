"""Every env var a Runner Job reads, and which side supplies it.

One image runs both modes now (`url4-cloud serve` / `url4-cloud run`), so this is a single
module rather than the two hand-synced copies it replaces. Two sources feed a Job's
environment, and the run mode cannot tell them apart — it just reads its environment:

- PER-RUN, written by the App onto the Job spec (:data:`WRITTEN_BY_APP`). None of it exists
  until a request arrives, which is exactly why Helm cannot supply it.
- PER-DEPLOY, named AND valued by the Helm chart and injected wholesale with ``envFrom``
  (:data:`DEPLOY_TIME`). The App never writes these — the chart is the only writer, so there is
  nothing to keep in sync.

These names are url4-cloud's, not the engine's: half are aigateway-specific and the rest
describe how this app schedules a run. None of it is part of the url4 language or its wire
format.
"""

from __future__ import annotations

# --- per-run: written by the App onto the Job spec -------------------------------------------
TOPIC = "URL4_CLOUD_TOPIC"
EXPRESSION = "URL4_CLOUD_EXPRESSION"
JOB_DEADLINE_S = "URL4_CLOUD_JOB_DEADLINE_S"
TRACEPARENT = "URL4_CLOUD_TRACEPARENT"

AIGATEWAY_TOKEN = "AIGATEWAY_TOKEN"
"""The CALLER's forwarded credential — a per-Job Secret created and deleted around one run."""

AIGATEWAY_PROFILE = "AIGATEWAY_PROFILE"
"""Per-request profile selection; absent means the gateway's default."""

# --- per-deploy: named by the chart, injected via envFrom ------------------------------------
NATS_URL = "URL4_CLOUD_NATS_URL"
AIGATEWAY_BASE_URL = "AIGATEWAY_BASE_URL"

AIGATEWAY_MODEL = "AIGATEWAY_MODEL"
"""Overrides the default route declared in the image's `url4.toml` (`config.aigatewayModel`)."""

TAVILY_API_KEY = "TAVILY_API_KEY"
"""Injected from the Tavily Secret by `envFrom`, so the Secret's KEY must be this exact name.
Absent => web tools stay off."""

RUNNER_CONFIG = "URL4_RUNNER_CONFIG"
"""Path to the declared world (:mod:`url4_cloud.runner.config`). Baked into the image; the App
never writes it."""

DEFAULT_NATS_URL = "nats://localhost:4222"
"""Fallback for an unset :data:`NATS_URL`. Lives beside the name it defaults so the two cannot
drift — every reader of the variable needs the same answer for "and if it is absent?"."""

# --- the sets the adapters and their tests are keyed off -------------------------------------
SECRET = frozenset({AIGATEWAY_TOKEN})
"""Values that must NEVER appear literally in a Job spec.

A Job object is not a secret store — it is readable with ``get jobs`` RBAC alone, echoed by
``kubectl describe``/``-o yaml``, and captured in the create-call audit log. These travel by
reference (``valueFrom.secretKeyRef``); `test_job_env_contract.py` pins that, keyed off this set.
"""

REQUIRED = frozenset({TOPIC, EXPRESSION})
"""Absent ⇒ run mode raises ``RunnerConfigError`` at boot. Every adapter must write these."""

WRITTEN_BY_APP = frozenset(
    {TOPIC, EXPRESSION, JOB_DEADLINE_S, TRACEPARENT, AIGATEWAY_TOKEN, AIGATEWAY_PROFILE}
)
"""The per-run subset. A key the App writes that is NOT in here reaches nothing — the direction
that breaks silently is an unread WRITE, not an unwritten READ (which simply falls back)."""

DEPLOY_TIME = frozenset(
    {NATS_URL, AIGATEWAY_BASE_URL, AIGATEWAY_MODEL, TAVILY_API_KEY, RUNNER_CONFIG}
)
"""Helm owns these end-to-end. The App writing one would make it two sources of truth again."""

__all__ = [
    "AIGATEWAY_BASE_URL",
    "AIGATEWAY_MODEL",
    "AIGATEWAY_PROFILE",
    "AIGATEWAY_TOKEN",
    "DEFAULT_NATS_URL",
    "DEPLOY_TIME",
    "EXPRESSION",
    "JOB_DEADLINE_S",
    "NATS_URL",
    "REQUIRED",
    "RUNNER_CONFIG",
    "SECRET",
    "TAVILY_API_KEY",
    "TOPIC",
    "TRACEPARENT",
    "WRITTEN_BY_APP",
]
