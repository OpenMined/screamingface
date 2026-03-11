"""Manage shell environment variables in the user's profile (.zshrc/.bashrc).

Adds and removes a marker-delimited block of exports so Claude Code
(and other tools) automatically point at the ScreamingFace server.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_BEGIN = "# screamingface-claude-env-begin"
MARKER_END = "# screamingface-claude-env-end"


def shell_profile() -> Path:
    """Return the user's shell profile path."""
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return Path.home() / ".zshrc"
    return Path.home() / ".bashrc"


def add_exports(env_vars: dict[str, str]) -> None:
    """Add a marker block of exports to the shell profile.

    Replaces any existing block to keep values current.
    """
    profile = shell_profile()
    content = profile.read_text() if profile.exists() else ""

    # Remove existing block
    content = _strip_marker_block(content)

    # Build new block
    lines = [MARKER_BEGIN]
    for key, value in env_vars.items():
        lines.append(f'export {key}="{value}"')
    lines.append(MARKER_END)
    block = "\n".join(lines) + "\n"

    if not content.endswith("\n") and content:
        content += "\n"

    profile.write_text(content + block)
    logger.info("Added exports to %s: %s", profile, list(env_vars.keys()))


def remove_exports() -> None:
    """Remove the marker block from the shell profile."""
    profile = shell_profile()
    if not profile.exists():
        return

    content = profile.read_text()
    if MARKER_BEGIN not in content:
        logger.info("No claude-env exports found in %s", profile)
        return

    new_content = _strip_marker_block(content)
    profile.write_text(new_content)
    logger.info("Removed claude-env exports from %s", profile)


def has_exports() -> bool:
    """Check if the marker block exists in the shell profile."""
    profile = shell_profile()
    if not profile.exists():
        return False
    return MARKER_BEGIN in profile.read_text()


def current_exports() -> dict[str, str]:
    """Parse the current marker block and return the env vars."""
    profile = shell_profile()
    if not profile.exists():
        return {}

    content = profile.read_text()
    result: dict[str, str] = {}
    inside = False
    for line in content.splitlines():
        if line.rstrip() == MARKER_BEGIN:
            inside = True
            continue
        if line.rstrip() == MARKER_END:
            break
        if inside and line.startswith("export "):
            # Parse: export KEY="VALUE"
            rest = line[len("export ") :]
            if "=" in rest:
                key, value = rest.split("=", 1)
                result[key] = value.strip('"')
    return result


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
