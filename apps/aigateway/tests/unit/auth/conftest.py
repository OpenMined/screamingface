from __future__ import annotations

import pytest_asyncio
from tortoise.contrib.test import tortoise_test_context


@pytest_asyncio.fixture
async def db():
    async with tortoise_test_context(["aigateway.core.auth.models"]):
        yield
