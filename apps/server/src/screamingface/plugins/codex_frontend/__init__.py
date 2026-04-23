"""codex-frontend plugin — transparent proxy for Codex CLI on a dedicated port.

Mirrors claude-frontend architecture: runs its own HTTP server so routes
don't clash with the main SF server. Intercepts /v1/responses traffic
from the Codex CLI and injects url4-resolved context.
"""
