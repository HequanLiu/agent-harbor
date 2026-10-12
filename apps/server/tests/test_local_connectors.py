"""Exercise connectors through a real local SDK workspace and application."""
from functools import partial
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from agentscope.workspace import LocalWorkspace
from harbor.app import create_harbor_app
from harbor.connectors.workspace import PREFIX
from test_connectors import signup, package, connect_for


@pytest.fixture
def mcp_endpoint():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((body['method'], self.headers.get('Authorization')))
            if 'id' not in body:
                self.send_response(202)
                self.end_headers()
                return
            if body['method'] == 'initialize':
                result = {'protocolVersion': body['params']['protocolVersion'],
                          'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'local-test', 'version': '1'}}
            elif body['method'] == 'tools/call':
                result = {'content': [{'type': 'text', 'text': 'local connector works'}], 'isError': False}
            else:
                result = {'tools': []}
            encoded = json.dumps({'jsonrpc': '2.0', 'id': body['id'], 'result': result}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://localhost:{server.server_port}', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_local_connector_session_lifecycle(tmp_path, monkeypatch, mcp_endpoint):
    origin, calls = mcp_endpoint
    monkeypatch.setenv('HARBOR_WORKSPACE_MODE', 'trusted_single_user_local')
    monkeypatch.setenv('HARBOR_CONNECTOR_TOKEN_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('HARBOR_CONNECTOR_ALLOWED_ORIGINS', origin)
    monkeypatch.setenv('HARBOR_CONNECTOR_PUBLIC_URL', 'https://harbor.example')
    monkeypatch.setenv('HARBOR_CONNECTOR_BRIDGE_KEYS', '{}')
    app = create_harbor_app(tmp_path)
    with TestClient(app) as client:
        me = signup(client, 'local@example.test')
        tenant, owner = me['active_tenant_id'], me['user']['id']
        agent = client.post('/agent/', json={'name': 'Local connector test'}).json()['agent_id']
        session = client.post('/sessions/', json={'agent_id': agent, 'name': 'Connected'}).json()['session_id']
        second = client.post('/sessions/', json={'agent_id': agent, 'name': 'Unselected'}).json()['session_id']
        imported = client.post('/harbor/connectors/import', content=package(url=origin + '/mcp'), headers={'Content-Type': 'application/zip'})
        assert imported.status_code == 201, imported.text
        cid = imported.json()['id']
        connect_for(app, me, cid)
        url = f'/harbor/connectors/sessions/{agent}/{session}'
        selected = client.put(url, json={'connector_ids': [cid]})
        assert selected.status_code == 200, selected.text
        ws = client.portal.call(app.state.workspace_service.resolve, tenant + '_' + owner, agent, session)
        assert isinstance(ws, LocalWorkspace)
        assert not (tmp_path / 'workspaces' / 'snapshots').exists()
        clients = client.portal.call(partial(ws.list_mcps, agent_id=agent, session_id=session))
        assert [c.name for c in clients] == [PREFIX + cid]
        assert clients[0].mcp_config.headers is None
        async def invoke():
            from mcp import ClientSession
            async with clients[0]._create_http_client() as (read, write, _):
                async with ClientSession(read, write) as session_client:
                    await session_client.initialize()
                    return await session_client.call_tool('echo', {'text': 'hello'})
        response = client.portal.call(invoke)
        assert not response.isError
        assert response.content[0].text == 'local connector works'
        assert ('tools/call', 'Bearer private-oauth-token') in calls
        assert client.portal.call(partial(ws.list_mcps, agent_id=agent, session_id=second)) == []
        skills = client.portal.call(partial(ws.list_skills, agent_id=agent))
        assert 'test-skill' in [s.name for s in skills]
        with pytest.raises(ValueError, match='Reserved'):
            client.portal.call(ws.add_mcp, SimpleNamespace(name=PREFIX + cid))
        with pytest.raises(ValueError, match='owner mismatch'):
            app.state.workspace_manager.connectors.wrap(ws, tenant, 'other')
        assert client.put(url, json={'connector_ids': []}).status_code == 200
        assert client.portal.call(partial(ws.list_mcps, agent_id=agent, session_id=session)) == []
