import pytest
from _fakes import STREAM_FACTORIES

from url4.streaming.testing.stream_contract import EventStreamFactory, assert_stream_conformance


@pytest.mark.asyncio
@pytest.mark.parametrize("make_stream", STREAM_FACTORIES)
async def test_adapter_satisfies_the_stream_contract(make_stream: EventStreamFactory) -> None:
    await assert_stream_conformance(make_stream)
