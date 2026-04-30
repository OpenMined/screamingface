from __future__ import annotations


class AigwError(Exception):
    """Base for every error raised by aigateway."""


class CredentialNotFoundError(AigwError):
    """No credential found in the OS store. User must run the provider's login flow."""


class AuthError(AigwError):
    """Credential present but unusable (malformed / refresh failed / scope rejected)."""
