"""Manage shell environment variables in the user's profile (.zshrc/.bashrc).

Adds and removes a marker-delimited block of exports so Claude Code
(and other tools) automatically point at the ScreamingFace server.
"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_BEGIN = "# screamingface-claude-env-intercept-begin"
MARKER_END = "# screamingface-claude-env-intercept-end"


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


def add_exports(env_vars: dict[str, str], extra_lines: list[str] | None = None) -> None:
    """Add a marker block of exports (and optional raw shell lines) to all shell profiles.

    Replaces any existing block to keep values current. ``extra_lines`` are written
    verbatim after the exports, inside the same marker block, so they are removed
    together with the exports on teardown.
    """
    lines = [MARKER_BEGIN]
    for key, value in env_vars.items():
        lines.append(f'export {key}="{value}"')
    if extra_lines:
        lines.extend(extra_lines)
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
        logger.info("Removed claude-env-intercept exports from %s", profile)


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


def render_gateway_banner(spec_name: str | None, expression: str | None) -> str:
    """Render the plain-text launch banner shown when the user starts ``claude``.

    Shows the active url4 spec + raw expression, or a warning when none is set.
    Plain ASCII (no ANSI) so it bakes cleanly into a shell rc file.
    """
    lines = [
        "  == ScreamingFace url4 ensemble gateway ==",
        "  Your claude queries are answered by this gateway, not api.anthropic.com.",
    ]
    if spec_name and expression:
        lines.append(f"  Active url4 spec: {spec_name}")
        lines.append(f"    {expression}")
    else:
        lines.append("  WARNING: no active url4 spec set — responses will be empty.")
        lines.append("    Set claude-frontend.active_spec in ScreamingFace settings.")
    return "\n".join(lines)


def build_claude_banner_function(banner_text: str) -> str:
    """Build a POSIX-sh ``claude()`` wrapper that prints ``banner_text`` to stderr
    then execs the real binary.

    One ``printf '%s\\n' '<quoted>' >&2`` per banner line, each quoted via
    ``shlex.quote`` so arbitrary url4 expressions cannot break out of the rc or be
    re-evaluated by the shell. ``command claude`` bypasses this function (no
    recursion); the banner never touches claude's stdout.
    """
    body = "\n".join(
        f"  printf '%s\\n' {shlex.quote(line)} >&2" for line in banner_text.split("\n")
    )
    return "claude() {\n" + body + '\n  command claude "$@"\n}'


def _strip_marker_block(content: str) -> str:
    """Remove everything between (and including) the marker lines."""
    from screamingface.core.marker_utils import strip_marker_block

    return strip_marker_block(content, MARKER_BEGIN, MARKER_END)
