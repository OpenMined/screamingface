"""The hexagonal adapters layer: concrete implementations of the `url4.streaming.interfaces`
ports (`JobRunner`, `EventPublisher`/`EventConsumer`) against real infrastructure — Kubernetes
Jobs (`k8s.py`) and NATS JetStream (`jetstream.py`). Wired in by `factory.py`, never imported
directly by core code.
"""
