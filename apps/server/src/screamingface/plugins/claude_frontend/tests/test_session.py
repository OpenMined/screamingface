"""Unit tests for the extracted ``SessionHook`` helper.

These test the hook shape in isolation — they don't spin up a real
proxy or talk to the session service. Hooks are mocked and asserted
on directly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from screamingface.plugins.claude_frontend._session import SessionHook


class TestSessionHookEnabled:
    def test_all_three_required(self):
        assert SessionHook(session_id="sid", service_url="url", hooks=MagicMock()).enabled
        assert not SessionHook(session_id=None, service_url="url", hooks=MagicMock()).enabled
        assert not SessionHook(session_id="sid", service_url=None, hooks=MagicMock()).enabled
        assert not SessionHook(session_id="sid", service_url="url", hooks=None).enabled


class TestEnrich:
    @pytest.mark.anyio
    async def test_disabled_returns_body_unchanged(self):
        hook = SessionHook(session_id=None, service_url=None, hooks=None)
        body = {"messages": [{"role": "user", "content": "hi"}]}
        result = await hook.enrich(body)
        assert result is body

    @pytest.mark.anyio
    async def test_snapshots_last_user_message(self):
        hooks = MagicMock()
        hooks.emit_async = AsyncMock(return_value=[None])
        hook = SessionHook(session_id="sid", service_url="url", hooks=hooks)
        body = {"messages": [{"role": "user", "content": "hi"}]}
        await hook.enrich(body)
        assert hook.original_user_msg == {"role": "user", "content": "hi"}

    @pytest.mark.anyio
    async def test_hook_modified_body_replaces(self):
        hooks = MagicMock()
        hooks.emit_async = AsyncMock(
            return_value=[None, {"messages": [{"role": "user", "content": "modified"}]}]
        )
        hook = SessionHook(session_id="sid", service_url="url", hooks=hooks)
        body = {"messages": [{"role": "user", "content": "original"}]}
        result = await hook.enrich(body)
        assert result["messages"][0]["content"] == "modified"

    @pytest.mark.anyio
    async def test_transport_error_swallowed(self):
        hooks = MagicMock()
        hooks.emit_async = AsyncMock(side_effect=httpx.ConnectError("down"))
        hook = SessionHook(session_id="sid", service_url="url", hooks=hooks)
        body = {"messages": []}
        result = await hook.enrich(body)  # should not raise
        assert result is body

    @pytest.mark.anyio
    async def test_unexpected_error_propagates(self):
        """Narrowed exception handling — unrelated bugs should surface."""
        hooks = MagicMock()
        hooks.emit_async = AsyncMock(side_effect=ValueError("bug"))
        hook = SessionHook(session_id="sid", service_url="url", hooks=hooks)
        with pytest.raises(ValueError, match="bug"):
            await hook.enrich({"messages": []})


class TestSave:
    @pytest.mark.anyio
    async def test_disabled_noop(self):
        hook = SessionHook(session_id=None, service_url=None, hooks=None)
        await hook.save({"id": "msg_1"}, streaming=False)  # should not raise

    @pytest.mark.anyio
    async def test_skips_when_no_original_user_message(self):
        hooks = MagicMock()
        hooks.emit_async = AsyncMock()
        hook = SessionHook(session_id="sid", service_url="url", hooks=hooks)
        # original_user_msg is None — save must skip
        await hook.save({"id": "msg_1"}, streaming=False)
        hooks.emit_async.assert_not_called()

    @pytest.mark.anyio
    async def test_emits_when_everything_set(self):
        hooks = MagicMock()
        hooks.emit_async = AsyncMock()
        hook = SessionHook(session_id="sid", service_url="url", hooks=hooks)
        hook.original_user_msg = {"role": "user", "content": "hi"}
        response = {"id": "msg_1", "content": []}
        await hook.save(response, streaming=True)
        hooks.emit_async.assert_awaited_once()
        name, kwargs = hooks.emit_async.call_args.args[0], hooks.emit_async.call_args.kwargs
        assert name == "session.save_response"
        assert kwargs["session_id"] == "sid"
        assert kwargs["response_body"] is response

    @pytest.mark.anyio
    async def test_transport_error_swallowed(self):
        hooks = MagicMock()
        hooks.emit_async = AsyncMock(side_effect=httpx.ConnectError("down"))
        hook = SessionHook(session_id="sid", service_url="url", hooks=hooks)
        hook.original_user_msg = {"role": "user", "content": "hi"}
        await hook.save({"id": "msg_1"}, streaming=False)  # should not raise


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
