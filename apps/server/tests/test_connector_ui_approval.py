import asyncio
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from mcp import ClientSession, types
from test_connector_ui import ui_fixture, create_call, signup


def test_stable_initialize_capability(monkeypatch):
    from harbor.connectors.ui_bridge import AppClientSession
    sent = []
    async def send(self, request, *args, **kwargs): sent.append(request)
    monkeypatch.setattr(ClientSession, 'send_request', send)
    session = object.__new__(AppClientSession)
    request = types.ClientRequest(types.InitializeRequest(params=types.InitializeRequestParams(
        protocolVersion=types.LATEST_PROTOCOL_VERSION, capabilities=types.ClientCapabilities(),
        clientInfo=types.Implementation(name='test', version='1'))))
    asyncio.run(session.send_request(request, types.InitializeResult))
    data = sent[0].model_dump(mode='json', by_alias=True, exclude_none=True)
    assert data['params']['capabilities']['extensions']['io.modelcontextprotocol/ui']['mimeTypes'] == ['text/html;profile=mcp-app']


def test_approval_requires_native_decision_and_is_one_use(tmp_path, monkeypatch):
    from harbor.connectors import ui_bridge
    app, ui, _ = ui_fixture(tmp_path, monkeypatch)
    tools = [types.Tool(name='prepare', inputSchema={'type': 'object'}, _meta={'ui': {'visibility': ['app']},
        'harbor/approval': {'prepareTool': 'prepare', 'executeTool': 'execute'}}),
        types.Tool(name='execute', inputSchema={'type': 'object'}, _meta={'ui': {'visibility': ['app']}})]
    executions = []
    async def invoke(oauth, network, tenant, owner, cid, method, params, **kwargs):
        if method == 'tools/list': return SimpleNamespace(tools=tools)
        if params['name'] == 'prepare': return {'content': [], 'structuredContent': {'approval': {
            'operation_id': 'op', 'title': 'Save', 'summary': 'approved summary', 'arguments': {'id': 1}, 'expires_at': int(time.time()) + 300}}}
        executions.append((params, kwargs))
        return {'content': [], 'structuredContent': {'saved': True}}
    monkeypatch.setattr(ui_bridge, 'invoke', invoke)
    with TestClient(app) as client:
        me = signup(client, 'approval@example.test')
        cid, token = create_call(app, ui, me)
        app.state.connector_ui_bridge_keys = {cid: 'test-bridge-key'}
        session = client.post('/harbor/connector-ui/sessions', json={'binding_token': token, 'agent_id': 'agent', 'session_id': 'chat'}).json()
        url = '/harbor/connector-ui/sessions/' + session['id'] + '/rpc'
        body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'prepare', 'arguments': {}}}
        challenge = client.post(url, json=body).json()['approval_required']
        assert not executions
        assert client.post(url, json={**body, 'params': {'name': 'execute'}}).status_code == 403
        decision = '/harbor/connector-ui/approvals/' + challenge['id'] + '/decision'
        assert client.post(decision, json={'approved': True, 'arguments': {'id': 2}}).status_code == 422
        assert client.post(decision, json={'approved': True}).json()['result']['structuredContent']['saved']
        assert client.post(decision, json={'approved': True}).status_code == 404
        assert len(executions) == 1
        assert executions[0][0]['arguments'] == {'id': 1}
        assert executions[0][1]['headers']['X-Harbor-Approval']
        cancelled = client.post(url, json=body).json()['approval_required']
        assert client.post('/harbor/connector-ui/approvals/' + cancelled['id'] + '/decision', json={'approved': False}).json()['cancelled']
        assert len(executions) == 1
