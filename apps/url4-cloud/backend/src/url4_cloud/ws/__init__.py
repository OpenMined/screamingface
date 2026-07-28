"""WebSocket layer: the FastAPI router that terminates client connections and the
in-process registry that tracks active per-topic subscribers.
"""

from url4_cloud.ws.endpoint import router
from url4_cloud.ws.registry import ConnectionRegistry

__all__ = ["ConnectionRegistry", "router"]
