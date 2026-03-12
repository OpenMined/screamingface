"""Manage shell environment variables in the user's profile (.zshrc/.bashrc).

Adds and removes a marker-delimited block of exports so Claude Code
(and other tools) automatically point at the ScreamingFace server.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_BEGIN = "# screamingface-claude-env-begin"
MARKER_END = "# screamingface-claude-env-end"


_RC_CANDIDATES = (
    ".bashrc",
    ".bash_profile",
    ".zshrc",
    ".zprofile",
    ".profile",
)


def shell_profiles() -> list[Path]:
    """Return all existing shell RC files that should be patched."""
    home = Path.home()
    profiles = [home / name for name in _RC_CANDIDATES if (home / name).exists()]
    if not profiles:
        # No RC files found — fall back to POSIX standard
        profiles = [home / ".profile"]
    return profiles


def add_exports(env_vars: dict[str, str]) -> None:
    """Add a marker block of exports to all shell profiles.

    Replaces any existing block to keep values current.
    """
    # Build new block
    lines = [MARKER_BEGIN]
    for key, value in env_vars.items():
        lines.append(f'export {key}="{value}"')
    lines.append(MARKER_END)
    block = "\n".join(lines) + "\n"

    for profile in shell_profiles():
        content = profile.read_text() if profile.exists() else ""
        content = _strip_marker_block(content)

        if not content.endswith("\n") and content:
            content += "\n"

        profile.write_text(content + block)
        logger.info("Added exports to %s: %s", profile, list(env_vars.keys()))


def remove_exports() -> None:
    """Remove the marker block from all shell profiles."""
    for profile in shell_profiles():
        if not profile.exists():
            continue
        content = profile.read_text()
        if MARKER_BEGIN not in content:
            continue
        new_content = _strip_marker_block(content)
        profile.write_text(new_content)
        logger.info("Removed claude-env exports from %s", profile)


def has_exports() -> bool:
    """Check if the marker block exists in any shell profile."""
    return any(p.exists() and MARKER_BEGIN in p.read_text() for p in shell_profiles())


def current_exports() -> dict[str, str]:
    """Parse the current marker block and return the env vars."""
    for profile in shell_profiles():
        if not profile.exists():
            continue
        content = profile.read_text()
        if MARKER_BEGIN not in content:
            continue
        result: dict[str, str] = {}
        inside = False
        for line in content.splitlines():
            if line.rstrip() == MARKER_BEGIN:
                inside = True
                continue
            if line.rstrip() == MARKER_END:
                break
            if inside and line.startswith("export "):
                rest = line[len("export ") :]
                if "=" in rest:
                    key, value = rest.split("=", 1)
                    result[key] = value.strip('"')
        return result
    return {}


def _strip_marker_block(content: str) -> str:
    """Remove everything between (and including) the marker lines."""
    lines = content.splitlines(keepends=True)
    result: list[str] = []
    inside = False
    for line in lines:
        if line.rstrip() == MARKER_BEGIN:
            inside = True
            continue
        if line.rstrip() == MARKER_END:
            inside = False
            continue
        if not inside:
            result.append(line)
    return "".join(result)
