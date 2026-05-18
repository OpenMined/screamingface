from __future__ import annotations

from typing import Any, cast

import pytest

from screamingface.plugins.gemini_backend_api.interpreter import GeminiBackendApiInterpreter
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart


class _CaptureBackend:
    def __init__(self) -> None:
        self.messages: list[CoreMessage] = []

    async def run(self, messages: list[CoreMessage], **_kwargs: Any) -> CoreMessage:
        self.messages = messages
        return CoreMessage(role="assistant", content="ok")


@pytest.mark.anyio
async def test_process_places_context_before_question() -> None:
    backend = _CaptureBackend()
    interpreter = GeminiBackendApiInterpreter(backend=cast(Any, backend))

    out = await interpreter.process(
        sources="The population of Paris is 2 million.",
        intent="Which city has the smallest population?",
    )

    assert out == "ok"
    content = backend.messages[0].content
    assert isinstance(content, list)
    assert isinstance(content[0], TextPart)
    assert content[0].text == (
        "Context:\nThe population of Paris is 2 million.\n\n"
        "Question:\nWhich city has the smallest population?\n\n"
        "Answer:"
    )
