import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from mcp.types import Tool, CallToolResult, TextContent

from test_connectors import api_fixture, signup, connect_for, package, oauth_fixture
from harbor.connectors.package import read_package


def test_ui_call_store_owner_session_epoch_and_encrypted_snapshot(tmp_path):
    from harbor.connectors.ui_store import UIStore
    store, cid, _, _, _ = oauth_fixture(tmp_path)
    store.save_grant('tenant_a', 'alice', cid, {'access_token': 'token'})
    store.bind('tenant_a', 'alice', cid, 'agent', 'chat')
    ui = UIStore(store)
    token = ui.record('tenant_a', 'alice', cid, 'agent', 'chat',
        {'name': 'crm_open', '_meta': {'ui': {'resourceUri': 'ui://crm/v1'}}},
        {'id': 2}, {'content': [], 'structuredContent': {'private': 'private-snapshot'}})
    assert ui.call('tenant_a', 'alice', token)['tool_result']['structuredContent']['private'] == 'private-snapshot'
    with pytest.raises(KeyError): ui.call('other', 'alice', token)
    with pytest.raises(KeyError): ui.call('tenant_a', 'bob', token)
    assert b'private-snapshot' not in store.path.read_bytes()
    store.replace_bindings('tenant_a', 'alice', 'agent', 'chat', [])
    with pytest.raises(ValueError): ui.call('tenant_a', 'alice', token)
    store.bind('tenant_a', 'alice', cid, 'agent', 'chat')
    store.disconnect('tenant_a', 'alice', cid)
    store.save_grant('tenant_a', 'alice', cid, {'access_token': 'new-token'})
    with pytest.raises(ValueError): ui.call('tenant_a', 'alice', token)


def test_model_app_visibility_and_raw_result_binding(tmp_path, monkeypatch):
    from harbor.connectors.workspace import make_client
    from harbor.connectors.ui_store import UIStore
    from harbor.connectors import ui_bridge
    async def scenario():
        store, cid, net, _, oauth = oauth_fixture(tmp_path)
        store.save_grant('tenant_a', 'alice', cid, {'access_token': 'token'})
        store.bind('tenant_a', 'alice', cid, 'agent', 'chat')
        tools = [Tool(name='open', inputSchema={'type': 'object'}, _meta={'ui': {'resourceUri': 'ui://crm/v1'}}),
                 Tool(name='save', inputSchema={'type': 'object'}, _meta={'ui': {'visibility': ['app']}})]
        async def list_raw(self):
            self._cached_tools = tools
            return tools
        from agentscope.mcp import MCPClient
        monkeypatch.setattr(MCPClient, 'list_raw_tools', list_raw)
        async def invoke(*args, **kwargs):
            if args[5] == 'tools/list': return SimpleNamespace(tools=tools)
            return CallToolResult(content=[TextContent(type='text', text='Readable fallback')], structuredContent={'id': 42}, _meta={'secret_for_app': True})
        monkeypatch.setattr(ui_bridge, 'invoke', invoke)
        client = make_client(oauth, net, 'tenant_a', 'alice', cid, agent='agent', session='chat')
        assert len(await client.list_tools()) == 1
        with pytest.raises(ValueError): await client.get_tool('save')
        result = await (await client.get_tool('open')).call(id=42)
        binding = result.metadata['connector_ui']
        assert result.content[0].text == 'Readable fallback'
        assert 'secret_for_app' not in str(result.metadata)
        saved = UIStore(store).call('tenant_a', 'alice', binding['binding_token'])
        assert saved['tool_input'] == {'id': 42}
        assert saved['tool_result']['structuredContent'] == {'id': 42}
        assert saved['tool_result']['_meta']['secret_for_app'] is True
    asyncio.run(scenario())


def ui_fixture(tmp_path, monkeypatch):
    from harbor.connectors.ui_store import UIStore
    from harbor.connectors import ui_bridge
    app = api_fixture(tmp_path)
    async def get_session(owner, agent, session):
        return object() if agent == 'agent' and session == 'chat' else None
    app.state.storage = SimpleNamespace(get_session=get_session)
    calls = []
    tools = [Tool(name='open', inputSchema={'type': 'object'}, _meta={'ui': {'resourceUri': 'ui://crm/v1'}}),
        Tool(name='save', inputSchema={'type': 'object'}, _meta={'ui': {'visibility': ['app']}}),
        Tool(name='model_only', inputSchema={'type': 'object'}, _meta={'ui': {'visibility': ['model']}})]
    async def invoke(oauth, network, tenant, user, cid, method, params, **kwargs):
        calls.append((method, params, kwargs))
        if method == 'tools/list': return SimpleNamespace(tools=tools)
        if method == 'resources/read':
            return {'contents': [{'uri': params['uri'], 'mimeType': 'text/html;profile=mcp-app', 'text': '<html>CRM</html>'}]}
        return {'content': [{'type': 'text', 'text': 'Saved'}], 'structuredContent': {'saved': True}}
    monkeypatch.setattr(ui_bridge, 'invoke', invoke)
    return app, UIStore(app.state.connector_store), calls


def create_call(app, ui, me):
    tenant, user = me['active_tenant_id'], me['user']['id']
    cid = app.state.connector_store.install(tenant, user, read_package(package()))['id']
    connect_for(app, me, cid)
    app.state.connector_store.bind(tenant, user, cid, 'agent', 'chat')
    token = ui.record(tenant, user, cid, 'agent', 'chat',
        {'name': 'open', '_meta': {'ui': {'resourceUri': 'ui://crm/v1'}}},
        {'id': 7}, {'content': [{'type': 'text', 'text': 'CRM fallback'}], 'structuredContent': {'id': 7}})
    return cid, token


def test_session_rpc_is_scoped_and_rechecks_authorization(tmp_path, monkeypatch):
    app, ui, calls = ui_fixture(tmp_path, monkeypatch)
    with TestClient(app) as alice, TestClient(app) as bob:
        me = signup(alice, 'alice@example.test')
        signup(bob, 'bob@example.test')
        cid, token = create_call(app, ui, me)
        body = {'binding_token': token, 'agent_id': 'agent', 'session_id': 'chat'}
        base = '/harbor/connector-ui/sessions'
        assert bob.post(base, json=body).status_code == 404
        assert alice.post(base, json={**body, 'session_id': 'other'}).status_code == 404
        response = alice.post(base, json=body)
        assert response.status_code == 200, response.text
        state = response.json()
        assert state['tool_result']['structuredContent'] == {'id': 7}
        url = base + '/' + state['id'] + '/rpc'
        rpc = {'jsonrpc': '2.0', 'id': 1, 'method': 'resources/read', 'params': {'uri': 'ui://crm/v1'}}
        assert alice.post(url, json=rpc).json()['result']['contents'][0]['text'] == '<html>CRM</html>'
        assert alice.post(url, json={**rpc, 'params': {'uri': 'https://evil.test/'}}).status_code == 403
        assert bob.post(url, json=rpc).status_code == 404
        call = {**rpc, 'method': 'tools/call', 'params': {'name': 'save', 'arguments': {'id': 7}}}
        assert alice.post(url, json=call).json()['result']['structuredContent']['saved']
        assert alice.post(url, json={**call, 'params': {**call['params'], '_meta': {'progressToken': 'sdk-token'}}}).status_code == 200
        assert alice.post(url, json={**call, 'params': {'name': 'model_only'}}).status_code == 403
        app.state.connector_store.replace_bindings(me['active_tenant_id'], me['user']['id'], 'agent', 'chat', [])
        before = len(calls)
        assert alice.post(url, json=call).status_code == 403
        assert len(calls) == before
