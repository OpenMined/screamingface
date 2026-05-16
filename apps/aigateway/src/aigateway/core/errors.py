from __future__ import annotations


class AigwError(Exception):
    """Base for every error raised by aigateway."""


class CredentialNotFoundError(AigwError):
    """No credential found in the OS store. User must run the provider's login flow."""


class AuthError(AigwError):
    """Credential present but unusable (malformed / refresh failed / scope rejected)."""


class ProfileNotFoundError(AigwError):
    """No profile found for the given (provider, name)."""


class ProfilePendingAuthError(AigwError):
    """Profile exists but is still in 'pending' state — auth not complete."""


class BootstrapError(AigwError):
    """Failed to bootstrap the gateway profile index from provider credentials."""
