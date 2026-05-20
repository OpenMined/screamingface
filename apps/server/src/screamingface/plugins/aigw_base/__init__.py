"""Shared base classes for aigw_*_backend plugins."""

from .auth_proxy_router import build_aigw_auth_proxy_router
from .backend import AigwBackend, AigwGatewayError
from .interpreter import AigwInterpreter
from .plugin_base import AigwBackendApiPluginBase
from .profile_defaults import build_profile_defaults_from_settings
from .settings import AigwBackendApiSettingsBase, AigwBaseSettings

__all__ = [
    "AigwBackend",
    "AigwBackendApiPluginBase",
    "AigwBackendApiSettingsBase",
    "AigwBaseSettings",
    "AigwGatewayError",
    "AigwInterpreter",
    "build_aigw_auth_proxy_router",
    "build_profile_defaults_from_settings",
]
