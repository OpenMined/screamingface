"""gemini-backend-api plugin — Google AI Gemini API via Gemini CLI credentials.

Ensemble backend for Google Gemini models. Same route shapes as
claude-backend-api at ``/gemini/*`` prefix, authenticated via the
Gemini CLI credential store.

Does NOT conflict with claude-backend-api or codex-backend-api — all
three coexist for ensemble fan-out.
"""
