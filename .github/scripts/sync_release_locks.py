#!/usr/bin/env python3
"""Regenerate the uv lockfiles on release-please's open release branches.

WHY THIS EXISTS
---------------
release-please bumps `version` in a package's `pyproject.toml` and nothing else. Every
`uv.lock` records that same version — its own workspace's editable root entry, and for
`apps/url4-cloud` also the editable `url4` path dependency it pins. So a release PR opens
with a lockfile that no longer matches its `pyproject.toml`, and `url4-cloud-tests` fails
on its first step (`uv lock --check`) before ruff, pyright or pytest ever run. `main` then
goes red the same way once the release merges.

That defect shipped three times (fixed by hand in f2b46c06 and 9061f40f, then again on
PR #504). This script closes the loop: the release PR is re-locked in the same job that
opens it, so it is correct from the moment it exists.

Every workspace is re-locked, not just the released one, because the version churn crosses
workspace boundaries: releasing `packages/url4` invalidates `apps/url4-cloud/uv.lock` too.
A workspace whose lock is already current re-locks to a no-op, so the sweep is safe and it
also heals drift that arrived by some other route.

`uv lock` (no `--upgrade`) is minimal-change: it rewrites only what the `pyproject.toml`
now requires and leaves every other pin alone. A release commit therefore never smuggles in
a dependency bump.

INPUT
-----
`RELEASE_PRS` — the `prs` output of googleapis/release-please-action (a JSON array of pull
requests, each with a `headBranchName`). Read from the environment rather than interpolated
into the workflow's `run:` block, so no branch name reaches a shell context.

The caller must already have a checkout with push credentials (see
`.github/workflows/release-please.yml`). Each branch is re-locked in its own `git worktree`
so this script's own checkout is never switched out from under it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# release-please attributes its own commits to this identity; the lock sync is part of the
# same release commit set and should not look like it came from a human.
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

COMMIT_MESSAGE = "chore(release): sync the uv lockfiles with the version bump"


def run(argv: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    """Run a command with no shell, failing loudly."""
    print(f"+ {' '.join(argv)}" + (f"  (in {cwd})" if cwd else ""), flush=True)
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else ""


def workspaces(worktree: Path) -> list[Path]:
    """Every directory in the checkout that owns a uv lockfile."""
    tracked = run(
        ["git", "-C", str(worktree), "ls-files", "*uv.lock"], capture=True
    ).split()
    return [worktree / lock for lock in tracked]


def sync_branch(branch: str) -> None:
    run(["git", "fetch", "origin", branch])

    with tempfile.TemporaryDirectory() as tmp:
        worktree = Path(tmp) / "release"
        run(["git", "worktree", "add", "--detach", str(worktree), "FETCH_HEAD"])
        try:
            for lock in workspaces(worktree):
                run(["uv", "lock"], cwd=lock.parent)

            dirty = run(
                ["git", "-C", str(worktree), "status", "--porcelain"], capture=True
            ).strip()
            if not dirty:
                print(f"{branch}: lockfiles already current", flush=True)
                return

            print(f"{branch}: re-locked\n{dirty}", flush=True)
            run(["git", "-C", str(worktree), "commit", "-am", COMMIT_MESSAGE])
            # Pushing with a PAT (never GITHUB_TOKEN) is what makes this worth doing: a
            # GITHUB_TOKEN push raises no workflow events, so the release PR would keep the
            # red check it was opened with even though the lockfiles are now correct.
            run(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "push",
                    "origin",
                    f"HEAD:refs/heads/{branch}",
                ]
            )
        finally:
            run(["git", "worktree", "remove", "--force", str(worktree)])


def main() -> int:
    payload = os.environ.get("RELEASE_PRS", "").strip()
    if not payload:
        print("RELEASE_PRS is empty — release-please opened no pull request.")
        return 0

    branches = [pr["headBranchName"] for pr in json.loads(payload)]
    if not branches:
        print("No release branches to sync.")
        return 0

    run(["git", "config", "user.name", BOT_NAME])
    run(["git", "config", "user.email", BOT_EMAIL])

    for branch in branches:
        sync_branch(branch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
