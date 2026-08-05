"""Executable contract for the local AI Gateway notebook launcher."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[3]
_LAUNCHER = _APP_ROOT / "run-dev-gateway.sh"


def test_local_launcher_migrates_then_inherits_canonical_openrouter_model_seeds(
    tmp_path: Path,
) -> None:
    """Local tooling prepares storage before serving and does not replace the model catalogue."""
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        "printf 'argv=%s\\n' \"$*\"\n"
        "printf 'auth=%s\\n' \"${AIGATEWAY_AUTH_ENABLED-unset}\"\n"
        "printf 'openrouter=%s\\n' \"${AIGW_OPENROUTER_ENABLED-unset}\"\n"
        "printf 'models=%s\\n' \"${AIGW_OPENROUTER_DEFAULT_MODELS-unset}\"\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    environment = os.environ.copy()
    environment.pop("AIGW_OPENROUTER_DEFAULT_MODELS", None)
    environment["PATH"] = f"{tmp_path}{os.pathsep}{environment['PATH']}"

    completed = subprocess.run(
        [_LAUNCHER],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert completed.stdout.splitlines() == [
        "argv=run aigateway migrate",
        "auth=0",
        "openrouter=true",
        "models=unset",
        "argv=run aigateway",
        "auth=0",
        "openrouter=true",
        "models=unset",
    ]
