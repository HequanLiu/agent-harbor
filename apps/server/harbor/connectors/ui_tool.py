"""AgentScope adapter preserving raw MCP App results outside model content."""
from agentscope.tool import MCPTool, ToolChunk
from agentscope.message import ToolResultState
from mcp.types import CallToolResult
from . import ui_bridge
from .ui_store import UIStore


class ConnectorTool(MCPTool):
    def __init__(self, client, tool):
        super().__init__(mcp_name=client.name, tool=tool, client_gen=client._get_client_gen,
            timeout=client.execution_timeout)
        self.connector_client = client

    async def call(self, **kwargs):
        c = self.connector_client
        # A client can outlive a chat selection; recheck at invocation time.
        if c._agent and c._chat and c._connector not in c._oauth.store.bindings(c._tenant, c._owner, c._agent, c._chat):
            raise ValueError('Connector is no longer selected in this chat')
        result = await ui_bridge.invoke(c._oauth, c._network, c._tenant, c._owner, c._connector,
            'tools/call', {'name': self._tool.name, 'arguments': kwargs})
        raw = ui_bridge.wire(result)
        result = CallToolResult.model_validate(raw)
        metadata = {}
        tool = ui_bridge.wire(self._tool)
        uri = (tool.get('_meta') or {}).get('ui', {}).get('resourceUri')
        if isinstance(uri, str) and uri.startswith('ui://') and c._agent and c._chat:
            try:
                token = UIStore(c._oauth.store).record(c._tenant, c._owner, c._connector, c._agent, c._chat, tool, kwargs, raw)
                metadata['connector_ui'] = {'binding_token': token, 'resource_uri': uri, 'tool_name': self._tool.name}
            except (KeyError, ValueError):
                # A changed grant or selection must not hide an already completed
                # business response, or prompt automatic replay of the mutation.
                pass
        return ToolChunk(content=self._convert_mcp_content_to_blocks(result.content),
            state=ToolResultState.ERROR if result.isError else ToolResultState.RUNNING, metadata=metadata)
