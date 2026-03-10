"""Shared test fixtures for ScreamingFace server tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.classes import ClassRegistry
from screamingface.core.config import AppConfig
from screamingface.core.hooks import HookRegistry


@pytest.fixture
def hooks() -> HookRegistry:
    return HookRegistry()


@pytest.fixture
def classes() -> ClassRegistry:
    return ClassRegistry()


@pytest.fixture
def app() -> FastAPI:
    config = AppConfig(plugins=[])
    return create_app(config)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
