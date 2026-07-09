---
id: OME-375
linear_url: https://linear.app/openmined/issue/OME-375/mock-websocket-service-docker-8000-random-ai-prompt-after-random-5-25
status: todo
type: task
priority: P2
labels: [repo, agentic, autonomous]
created: 2026-07-09
closed:
---

Mock WebSocket service for the nginx + AKS (k8s) load-test PoC: Docker image, WS server on
:8000; per connection/message responds with a random AI-style prompt after a uniform random
5–25 minute delay (long-lived-connection shape of slow ensemble runs). Configurable delay
bounds/keepalive/close-behavior via env; `/healthz` for probes; README with example k8s +
nginx ingress annotations (proxy_read_timeout / LB idle timeout are the things under test).
Landing label `repo` until a target app/dir is decided.
