"""Restricted official MCP transport. Targets come only from installed packages."""
import asyncio
import json
from mcp import ClientSession
from mcp import types

MAX_RESULT_BYTES = 2 * 1024 * 1024


class AppClientSession(ClientSession):
    async def send_request(self, request, *args, **kwargs):
        if isinstance(request.root, types.InitializeRequest):
            data = request.root.params.capabilities.model_dump(mode='json', by_alias=True, exclude_none=True)
            data.setdefault('extensions', {})['io.modelcontextprotocol/ui'] = {'mimeTypes': ['text/html;profile=mcp-app']}
            request.root.params.capabilities = types.ClientCapabilities.model_validate(data)
        return await super().send_request(request, *args, **kwargs)


def wire(value):
    result = value.model_dump(mode='json', by_alias=True, exclude_none=True) if hasattr(value, 'model_dump') else value
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RESULT_BYTES:
        raise ValueError('Connector result exceeds size limit')
    return result


def visible(tool, audience):
    data = wire(tool)
    visibility = (data.get('_meta') or {}).get('ui', {}).get('visibility', ['model', 'app'])
    return isinstance(visibility, list) and audience in visibility


async def invoke(oauth, network, tenant, owner, cid, method, params, *, headers=None):
    # Lazy import avoids workspace adapter cycle.
    from .workspace import make_client
    client = make_client(oauth, network, tenant, owner, cid)
    timeout = min(client.mcp_config.timeout, 60)
    async with asyncio.timeout(timeout):
        async with client._connector_transport(headers=headers) as transport:
            async with AppClientSession(transport[0], transport[1]) as session:
                await session.initialize()
                if method == 'tools/list':
                    tools, cursor, seen = [], None, set()
                    for _ in range(100):
                        page = await session.list_tools(cursor=cursor)
                        tools.extend(page.tools)
                        cursor = page.nextCursor
                        if not cursor: return types.ListToolsResult(tools=tools)
                        if cursor in seen: raise ValueError('Repeated tool discovery cursor')
                        seen.add(cursor)
                    raise ValueError('Tool discovery exceeds page limit')
                if method == 'resources/read': return wire(await session.read_resource(params['uri']))
                if method == 'tools/call': return await session.call_tool(params['name'], arguments=params.get('arguments', {}))
                raise ValueError('Unsupported MCP App method')
