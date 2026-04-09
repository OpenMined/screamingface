"""claude-backend-api plugin — direct Anthropic Messages API, OAuth from Keychain.

Drop-in replacement for the CLI-subprocess ``claude-backend`` plugin.
Same routes, same request/response shapes, same profile config.
Implementation replaces ``claude -p`` with a raw httpx POST to
``https://api.anthropic.com/v1/messages`` authenticated by the OAuth
bearer token read from the platform credential store
(``Claude Code-credentials``).

Conflicts with ``claude-backend`` — operators pick exactly one by listing
it in ``sf.json`` plugins array.
"""
