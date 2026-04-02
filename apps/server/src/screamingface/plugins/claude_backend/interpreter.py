"""Claude url4 interpreter — runs resolved expressions through the Claude CLI."""

from __future__ import annotations

import logging
import shutil
import tempfile
from typing import TYPE_CHECKING, Any

from screamingface.plugins.claude_backend.runner import run_claude
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter

if TYPE_CHECKING:
    from screamingface.plugins.claude_backend.plugin import ClaudeBackendSettings

logger = logging.getLogger(__name__)


class ClaudeInterpreter(Url4Interpreter):
    """Url4 interpreter that runs the combined prompt through Claude CLI.

    Each call creates a fresh temp directory and destroys it after the CLI
    exits, so Claude never loads project context (CLAUDE.md, git, etc.).

    Used by the ``GET /claude?q=`` endpoint.
    """

    def __init__(self, app: Any = None, settings: ClaudeBackendSettings | None = None):
        super().__init__(app)
        self.settings = settings

    async def process(self, sources: str, intent: str | None) -> str:
        combined = f"{intent}\n\n{sources}" if intent and sources else (intent or sources or "")
        args = self._build_args()
        timeout = self.settings.timeout_seconds if self.settings else 300.0
        tmp_dir = tempfile.mkdtemp(prefix="sf_claude_")
        try:
            _exit_code, stdout, _stderr, _duration = await run_claude(
                args, combined, timeout, cwd=tmp_dir,
            )
            return stdout
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _build_args(self) -> list[str]:
        args = ["claude", "-p"]
        if self.settings:
            args.extend(["--system-prompt", self.settings.interpreter_system_prompt])
            if self.settings.default_model:
                args.extend(["--model", self.settings.default_model])
        return args
