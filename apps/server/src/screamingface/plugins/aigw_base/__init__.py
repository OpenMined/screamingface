"""Shared base classes for aigw_*_backend plugins."""

from .auth_proxy_router import build_aigw_auth_proxy_router
from .backend import AigwBackend, AigwGatewayError
from .interpreter import AigwInterpreter
from .plugin_base import AigwBackendApiPluginBase
from .settings import AigwBackendApiSettingsBase

__all__ = [
    "AigwBackend",
    "AigwBackendApiPluginBase",
    "AigwBackendApiSettingsBase",
    "AigwGatewayError",
    "AigwInterpreter",
    "build_aigw_auth_proxy_router",
]
