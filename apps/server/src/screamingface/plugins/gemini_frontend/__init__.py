"""gemini-frontend plugin — transparent proxy for Gemini CLI on a dedicated port.

Mirrors claude-frontend/codex-frontend architecture: runs its own HTTP
server so routes don't clash with the main SF server. Intercepts traffic
from the Gemini CLI and injects url4-resolved context.
"""
