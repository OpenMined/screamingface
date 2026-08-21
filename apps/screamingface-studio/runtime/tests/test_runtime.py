from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from screamingface._runtime import server
from screamingface._runtime.config import bundled_runner_config
from screamingface_runtime.runtime import RuntimeConfig, run


def test_studio_uses_the_shared_runtime() -> None:
    assert run.__module__ == "screamingface._runtime.server"
    assert RuntimeConfig(data_dir=Path("/tmp/screamingface-studio-test")).services == {
        "gateway": "http://127.0.0.1:9105",
        "scoreboard": "http://127.0.0.1:9106",
        "engine": "http://127.0.0.1:9108",
    }


def test_external_shutdown_waiter_can_be_cancelled_before_event_is_set() -> None:
    async def cancel_waiter() -> None:
        task = asyncio.create_task(server._wait_for_thread_event(threading.Event()))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)

    asyncio.run(cancel_waiter())


def test_runtime_config_uses_persistent_databases(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)

    assert config.gateway_database_url == f"sqlite://{tmp_path}/aigateway.sqlite3"
    assert config.scoreboard_database_url == f"sqlite://{tmp_path}/scoreboard.sqlite3"


def test_bundled_runner_config_matches_the_deployment_config() -> None:
    deployment = (
        Path(__file__).resolve().parents[3] / "screamingface-engine" / "url4.toml"
    )

    assert (
        bundled_runner_config().read_text().rstrip() == deployment.read_text().rstrip()
    )
