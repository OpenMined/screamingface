"""Development server entrypoint for the persistent ScreamingFace engine."""

from __future__ import annotations

import importlib

from screamingface_engine.app import create_app
from screamingface_engine.settings import H11_MAX_INCOMPLETE_EVENT_SIZE, Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn = importlib.import_module("uvicorn")
    uvicorn.run(
        create_app(settings=settings),
        host=settings.host,
        port=settings.port,
        h11_max_incomplete_event_size=max(
            H11_MAX_INCOMPLETE_EVENT_SIZE,
            settings.max_request_target_bytes * 2,
        ),
    )


if __name__ == "__main__":  # pragma: no cover - console entrypoint
    main()
