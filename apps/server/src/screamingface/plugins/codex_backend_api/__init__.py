"""codex-backend-api plugin -- OpenAI Chat Completions API via Codex CLI OAuth.

Drop-in ensemble backend for OpenAI models. Same route shapes as
claude-backend-api (``/codex/run``, ``/codex?q=``, ``/codex/{profile}``),
authenticated by the OAuth bearer token read from the Codex CLI's
``~/.codex/auth.json`` credential file.

Does NOT conflict with ``claude-backend-api`` -- both plugins coexist so
the ensemble fan-out can dispatch to ``/claude()!intent`` and
``/codex()!intent`` in parallel.
"""
