"""Session: provider connections and API keys — Colab-native.

INVARIANT (spec I4): keys live only in memory (the per-process ``KeyStore``);
never written to disk, never printed, never put in a recipe/url — at most
masked to the last 4 characters. Keys resolve Colab Secret → environment
variable → masked prompt.

Honesty: inference is simulated (see ``engine.py``). Connecting a provider
stores its key and flips it to "connected" — the seam where real API calls
(OME-296) plug in, not real inference today.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .catalog import PROVIDERS

# provider_id -> the conventional env var / Colab secret name
KEY_NAMES: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepmind": "GEMINI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "hf": "HF_TOKEN",
}


def in_colab() -> bool:
    try:
        import google.colab  # type: ignore[import-not-found]  # noqa: F401

        return True
    except ImportError:
        return False


def in_notebook() -> bool:
    try:
        from IPython import get_ipython  # type: ignore[import-not-found]

        return get_ipython() is not None
    except ImportError:
        return False


def _colab_secret(name: str) -> str | None:
    try:
        from google.colab import userdata  # type: ignore[import-not-found]

        return userdata.get(name)
    except Exception:  # noqa: BLE001 — not in colab, or secret not granted: both mean "absent"
        return None


def _from_env_or_secret(provider_id: str) -> tuple[str | None, str]:
    """Look up a provider's key: Colab Secret first, then the environment."""
    name = KEY_NAMES.get(provider_id)
    if not name:
        return None, ""
    if in_colab():
        val = _colab_secret(name)
        if val:
            return val, "secret"
    val = os.environ.get(name)
    return val, ("env" if val else "")


def _mask(key: str) -> str:
    if not key:
        return ""
    return f"…{key[-4:]}" if len(key) > 4 else "…"


@dataclass
class Connection:
    provider_id: str
    connected: bool = False
    source: str = ""  # "secret" | "env" | "entered"


class KeyStore:
    """In-memory only. Keys never leave the process and are never echoed."""

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    def set(self, provider_id: str, key: str) -> None:
        self._keys[provider_id] = key

    def get(self, provider_id: str) -> str | None:
        return self._keys.get(provider_id)


class Session:
    def __init__(self) -> None:
        self.keys = KeyStore()
        self.connections: dict[str, Connection] = {}

    def connect(
        self,
        provider: str,
        api_key: str | None = None,
        prompt: bool | None = None,
    ) -> Connection:
        """Connect a provider. Key resolution: explicit → Colab Secret → env →
        masked getpass prompt (unless ``prompt=False``)."""
        pid = _resolve_provider(provider)
        prov = PROVIDERS[pid]
        conn = self.connections.setdefault(pid, Connection(pid))

        key, source = (api_key, "entered") if api_key else _from_env_or_secret(pid)
        if key is None and (prompt or (prompt is None and not in_notebook())):
            import getpass

            key = getpass.getpass(f"{prov.name} API key ({KEY_NAMES.get(pid, '')}): ")
            source = "entered"
        if not key:
            raise ValueError(
                f"No API key for {prov.name}. Pass api_key=…, or set the "
                f"{KEY_NAMES.get(pid)} "
                f"{'Colab Secret' if in_colab() else 'environment variable'}."
            )

        self.keys.set(pid, key)
        conn.connected, conn.source = True, source
        return conn

    def is_connected(self, provider_id: str) -> bool:
        c = self.connections.get(provider_id)
        return bool(c and c.connected)

    def status_rows(self) -> list[dict]:
        rows = []
        for pid, prov in PROVIDERS.items():
            c = self.connections.get(pid)
            key = self.keys.get(pid)
            rows.append(
                dict(
                    provider=prov.name,
                    kind=prov.kind,
                    connected=bool(c and c.connected),
                    source=(c.source if c else ""),
                    key=_mask(key) if key else "",
                )
            )
        return rows


# module-level singleton — the session the public verbs operate on
session = Session()


def _resolve_provider(provider: str) -> str:
    from .studio import _SLUG_PROVIDER

    if provider in PROVIDERS:
        return provider
    if provider in _SLUG_PROVIDER:  # studio slug, e.g. "google" -> "deepmind"
        return _SLUG_PROVIDER[provider]
    raise KeyError(f"Unknown provider {provider!r}. Known: {sorted(PROVIDERS)}.")


def connect(provider: str, api_key: str | None = None, prompt: bool | None = None) -> Connection:
    """Connect a model provider (Colab Secret → env var → masked prompt)."""
    return session.connect(provider, api_key=api_key, prompt=prompt)


def setup():
    """One-cell bootstrap: connect providers.

    In a notebook returns the connect panel (static in v0.1); headless it
    prints how to connect. Idempotent — call it whenever you want the panel back.
    """
    if not in_notebook():
        print(
            "screamingface setup (headless):\n"
            "  sf.connect('anthropic', api_key=...)   # or set ANTHROPIC_API_KEY\n"
            "  sf.connect('openai')                   # reads OPENAI_API_KEY\n"
            "Inference is simulated — keys mark providers connected, not billed."
        )
        return None
    from .widgets import setup_panel

    return setup_panel()
