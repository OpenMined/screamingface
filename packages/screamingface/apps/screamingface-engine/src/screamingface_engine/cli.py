"""Development server entrypoint for the persistent ScreamingFace engine."""

from __future__ import annotations

import importlib

from screamingface_engine.app import create_app
from screamingface_engine.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn = importlib.import_module("uvicorn")
    uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover - console entrypoint
    main()
