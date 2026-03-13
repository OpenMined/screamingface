"""Frontend registry — manages domain→port mappings for frontend plugins.

Frontend plugins (claude-frontend, gemini-frontend, etc.) each run their own
HTTP server on a dedicated port.  The registry persists a domain→target
mapping to ~/.screamingface/frontends.json so the mitmproxy addon can route
intercepted traffic to the correct frontend based on the original domain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

FRONTENDS_FILE = Path("~/.screamingface/frontends.json").expanduser()


@dataclass
class FrontendEntry:
    """A registered frontend with its listen address and domains."""

    plugin_name: str
    domains: list[str]
    host: str = "127.0.0.1"
    port: int = 9101
    scheme: str = "http"


class FrontendRegistry:
    """Tracks active frontend plugins and writes domain→target mapping to disk."""

    def __init__(self) -> None:
        self._entries: dict[str, FrontendEntry] = {}  # plugin_name → entry

    def register(self, entry: FrontendEntry) -> None:
        """Register a frontend and update the mapping file."""
        self._entries[entry.plugin_name] = entry
        self._write()
        logger.info(
            "Frontend registered: %s → %s:%d (%s)",
            entry.plugin_name,
            entry.host,
            entry.port,
            entry.domains,
        )

    def unregister(self, plugin_name: str) -> None:
        """Unregister a frontend and update the mapping file."""
        self._entries.pop(plugin_name, None)
        self._write()
        logger.info("Frontend unregistered: %s", plugin_name)

    def get_domain_map(self) -> dict[str, dict[str, object]]:
        """Return domain → {host, port, scheme} mapping for all frontends."""
        mapping: dict[str, dict[str, object]] = {}
        for entry in self._entries.values():
            for domain in entry.domains:
                mapping[domain] = {
                    "host": entry.host,
                    "port": entry.port,
                    "scheme": entry.scheme,
                }
        return mapping

    def get_all_domains(self) -> list[str]:
        """Return all domains across all registered frontends."""
        domains: list[str] = []
        for entry in self._entries.values():
            domains.extend(entry.domains)
        return domains

    @property
    def entries(self) -> dict[str, FrontendEntry]:
        return dict(self._entries)

    def _write(self) -> None:
        """Persist the domain mapping to disk for the mitmproxy addon."""
        FRONTENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        mapping = self.get_domain_map()
        FRONTENDS_FILE.write_text(json.dumps(mapping, indent=2))
        logger.debug("Frontend mapping written to %s", FRONTENDS_FILE)

    @staticmethod
    def clear_file() -> None:
        """Remove the mapping file."""
        if FRONTENDS_FILE.exists():
            FRONTENDS_FILE.unlink()
            logger.debug("Frontend mapping file removed")
