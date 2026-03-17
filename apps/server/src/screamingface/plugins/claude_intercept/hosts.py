"""/etc/hosts manipulation with marker-based entries."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

HOSTS_FILE = Path("/etc/hosts")
MARKER_BEGIN = "# screamingface-claude-intercept-begin"
MARKER_END = "# screamingface-claude-intercept-end"


def add_entries(domains: list[str], target: str = "127.0.0.1") -> None:
    """Append marker block to /etc/hosts mapping domains to target IP.

    Removes any existing marker block first to avoid duplicates.
    Requires sudo.
    """
    content = HOSTS_FILE.read_text()

    # Remove existing block if present
    content = _strip_marker_block(content)

    # Build new block
    lines = [MARKER_BEGIN]
    for domain in domains:
        lines.append(f"{target} {domain}")
    lines.append(MARKER_END)
    block = "\n".join(lines) + "\n"

    # Ensure trailing newline before our block
    if not content.endswith("\n"):
        content += "\n"

    new_content = content + block
    _write_hosts(new_content)
    logger.info("Added intercept entries for %s to /etc/hosts", domains)


def remove_entries() -> None:
    """Remove the marker block from /etc/hosts. Requires sudo."""
    content = HOSTS_FILE.read_text()
    if MARKER_BEGIN not in content:
        logger.info("No intercept entries found in /etc/hosts")
        return

    new_content = _strip_marker_block(content)
    _write_hosts(new_content)
    logger.info("Removed intercept entries from /etc/hosts")


def has_entries() -> bool:
    """Check if marker block exists in /etc/hosts."""
    return MARKER_BEGIN in HOSTS_FILE.read_text()


def flush_dns() -> None:
    """Flush the macOS DNS cache."""
    if sys.platform != "darwin":
        logger.warning("DNS flush only supported on macOS")
        return
    logger.info("Flushing DNS cache...")
    subprocess.run(
        ["sudo", "dscacheutil", "-flushcache"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["sudo", "killall", "-HUP", "mDNSResponder"],
        check=True,
        capture_output=True,
    )


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


def _write_hosts(content: str) -> None:
    """Write content to /etc/hosts via sudo tee."""
    subprocess.run(
        ["sudo", "tee", str(HOSTS_FILE)],
        input=content.encode(),
        stdout=subprocess.DEVNULL,
        check=True,
    )
