"""The DATA PLANE: executing one url4 expression and streaming its observation events.

This is what `url4-cloud run` enters — the mode a Kubernetes Job runs (`K8sJobRunner` schedules
the App's own image with that command). It reads its whole world from the Job's environment
(:mod:`url4_cloud.job_env`) and publishes to NATS; it serves no port and answers no request.

LAYERING: this subpackage and the control plane (`app`, `rest`, `ws`, `auth`, `catalog`,
`config`, `metrics`, `ops`, `schemas`, `adapters.k8s`, `adapters.factory`) MUST NOT import each
other. They share exactly three leaves — :mod:`url4_cloud.job_env`, :mod:`url4_cloud.subjects`
and :mod:`url4_cloud.adapters.jetstream` — and `.claude/scripts/check_layering.py` proves it.

WHY the rule outlived the package split it was born in: the two modes ship in one image and one
venv now, so nothing at runtime stops the run path from importing FastAPI or the kubernetes
client. Keeping the import graph disjoint is what holds a Job's cold start to the engine plus
httpx plus nats-py — the cost the separate slim image used to buy structurally.
"""
