import asyncio
import uuid
from collections.abc import Callable

import pytest
from _fakes import STREAM_FACTORIES, take
from pydantic import ValidationError

from url4.streaming.interfaces import EventStream
from url4.streaming.protocol import AttachData


def _topic() -> str:
    return f"bounds-{uuid.uuid4().hex[:8]}"


@pytest.mark.parametrize("bad", [0, -1])
def test_attach_data_rejects_from_sequence_below_one(bad: int) -> None:
    with pytest.raises(ValidationError):
        AttachData(from_sequence=bad)


@pytest.mark.parametrize("ok", [None, 1, 2])
def test_attach_data_accepts_none_and_one_based_values(ok: int | None) -> None:
    assert AttachData(from_sequence=ok).from_sequence == ok


@pytest.mark.asyncio
@pytest.mark.parametrize("make_stream", STREAM_FACTORIES)
@pytest.mark.parametrize("cursor", [None, 1])
async def test_conformance_subscribe_still_accepts_one_and_none(
    make_stream: Callable[[], EventStream], cursor: int | None
) -> None:
    stream = make_stream()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.25):
            await take(stream, _topic(), 1, cursor)
