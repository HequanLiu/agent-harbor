"""UI associations survive the real event/history path without model exposure."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agentscope.event import ToolResultStartEvent, ToolResultEndEvent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg, ToolCallBlock, ToolResultBlock
from agentscope.tool import ToolChunk, ToolResponse


def test_binding_survives_tool_chunk_sse_and_history_serialization():
    binding = {'binding_token': 'opaque-ui-binding-sentinel',
               'resource_uri': 'ui://crm/opportunity', 'tool_name': 'crm_create'}
    response = ToolResponse().append_chunk(ToolChunk(
        content=[], state='success', metadata={'connector_ui': binding}))
    message = Msg(name='assistant', role='assistant', content=[])
    message.append_event(ToolResultStartEvent(
        reply_id=message.id, tool_call_id='call-1', tool_call_name='crm_create'))
    end = ToolResultEndEvent(reply_id=message.id, tool_call_id='call-1',
                            state=response.state, metadata=response.metadata)
    message.append_event(ToolResultEndEvent.model_validate_json(end.model_dump_json()))
    restored = Msg.model_validate_json(message.model_dump_json())
    assert restored.content[0].metadata['connector_ui'] == binding


def test_model_formatter_does_not_receive_ui_binding_metadata():
    message = Msg(name='assistant', role='assistant', content=[
        ToolCallBlock(id='call-1', name='crm_create', input='{}'),
        ToolResultBlock(id='call-1', name='crm_create', output='Created opportunity',
                        state='success', metadata={'connector_ui': {
                            'binding_token': 'opaque-ui-binding-sentinel'}}),
    ])
    formatted = asyncio.run(OpenAIChatFormatter().format([message]))
    encoded = json.dumps(formatted, default=str)
    assert 'Created opportunity' in encoded
    assert 'opaque-ui-binding-sentinel' not in encoded
    assert 'connector_ui' not in encoded


@pytest.mark.parametrize('has_content', [True, False])
def test_background_binding_survives_inbox_sse_history_without_model_exposure(has_content):
    from agentscope.app.middleware._tool_offload_middleware import ToolOffloadMiddleware
    from agentscope.app.middleware._inbox_middleware import InboxMiddleware
    from agentscope.app.message_bus import InMemoryMessageBus
    from agentscope.event import HintBlockEvent
    from agentscope.message import TextBlock

    async def run():
        binding = {'binding_token': 'background-binding-sentinel',
                   'resource_uri': 'ui://mes/editor', 'tool_name': 'create'}
        bus = InMemoryMessageBus()
        manager = SimpleNamespace(register_task=AsyncMock(return_value='bg-1'))
        tool = SimpleNamespace(is_state_injected=False, is_external_tool=False)
        agent = SimpleNamespace(name='Agent', toolkit=SimpleNamespace(get_tool=AsyncMock(return_value=tool)),
                                state=SimpleNamespace(session_id='s', reply_id='r', context=[]))
        release = asyncio.Event()

        async def execute(**kwargs):
            await release.wait()
            yield ToolResponse(content=[TextBlock(text='Created draft')] if has_content else [],
                               state='success', metadata={'connector_ui': binding})

        middleware = ToolOffloadMiddleware(manager, bus, 'user', 'agent', timeout_secs=0.001)
        result = [item async for item in middleware.on_acting(agent, {
            'tool_call': ToolCallBlock(id='call-1', name='create', input='{}')}, execute)]
        assert 'running in background' in result[-1].content[0].text
        release.set()

        async def next_handler(**kwargs):
            if False:
                yield

        inbox = InboxMiddleware(bus)
        events = []
        async with asyncio.timeout(2):
            while not events:
                events = [event async for event in inbox.on_reasoning(agent, {}, next_handler)]
                await asyncio.sleep(0)
        event = HintBlockEvent.model_validate_json(events[0].model_dump_json())
        assert event.metadata['connector_ui'] == binding
        message = Msg(id='r', name='Agent', role='assistant', content=[])
        message.append_event(event)
        restored = Msg.model_validate_json(message.model_dump_json())
        assert restored.content[0].metadata['connector_ui'] == binding
        encoded = json.dumps(await OpenAIChatFormatter().format([restored]), default=str)
        assert 'background-binding-sentinel' not in encoded
        assert 'connector_ui' not in encoded

    asyncio.run(run())
