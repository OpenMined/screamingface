from __future__ import annotations

from typing import Any

from aigateway.core.plugin_base import ModelEntry, ProviderPluginBase

from .discovery import discover_ollama_models, resolve_ollama_host

_CLIENT_AUTH_HEADER_NAMES = {"authorization", "x-api-key", "proxy-authorization"}


class OllamaProviderPlugin(ProviderPluginBase):
    custom_llm_provider = "ollama"

    def register_models(self) -> list[ModelEntry]:
        host = resolve_ollama_host()
        return [
            ModelEntry(
                model_name=f"ollama/{name}",
                litellm_params={"model": f"ollama_chat/{name}", "api_base": host},
            )
            for name in discover_ollama_models(host)
        ]

    def allows_chatless_profile(self) -> bool:
        return True

    def prepare_chat_body(self, body: dict[str, Any]) -> dict[str, Any]:
        """Sanitize caller auth and adapt Ollama model/api_base for LiteLLM."""
        out = dict(body)
        out.pop("api_key", None)
        extra_headers = out.get("extra_headers")
        if isinstance(extra_headers, dict):
            sanitized_headers = {
                key: value
                for key, value in extra_headers.items()
                if str(key).lower() not in _CLIENT_AUTH_HEADER_NAMES
            }
            if sanitized_headers:
                out["extra_headers"] = sanitized_headers
            else:
                out.pop("extra_headers", None)
        elif "extra_headers" in out:
            out.pop("extra_headers", None)

        out["api_base"] = resolve_ollama_host()
        model = out.get("model")
        if isinstance(model, str) and model.startswith("ollama/"):
            out["model"] = f"ollama_chat/{model.split('/', 1)[1]}"
        # routes/chat.py resolves the provider before this rewrite; do not
        # re-derive the provider from body["model"] after this point.
        return out


PLUGIN = OllamaProviderPlugin()
