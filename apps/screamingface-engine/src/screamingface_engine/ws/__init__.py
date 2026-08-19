"""WebSocket layer: the FastAPI router that terminates client connections and the
in-process registry that tracks active per-topic subscribers.
"""

from screamingface_engine.ws.endpoint import router
from screamingface_engine.ws.registry import AudienceListener, ConnectionRegistry

__all__ = ["AudienceListener", "ConnectionRegistry", "router"]
