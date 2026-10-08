import asyncio

from fastapi.testclient import TestClient

from harbor.app import create_harbor_app
from harbor.workspaces import TenantWorkspaceManager
from test_auth import register


def test_real_agent_session_isolation_and_persistence(tmp_path):
    app = create_harbor_app(tmp_path)
    with TestClient(app) as alice, TestClient(app) as bob:
        a = register(alice)
        register(bob, 'bob@example.test')
        agent = alice.post('/agent/', json={'name': 'Harbor assistant'})
        assert agent.status_code == 201, agent.text
        agent_id = agent.json()['agent_id']
        session = alice.post('/sessions/', json={'agent_id': agent_id, 'name': 'Persist me'})
        assert session.status_code == 201, session.text
        session_id = session.json()['session_id']
        for route in ['/workspace/directories', '/workspace/files']:
            denied = alice.get(route, params={'agent_id': agent_id, 'session_id': session_id, 'path': str(tmp_path.parent)})
            assert denied.status_code == 403, (route, denied.text)
        token_denied = alice.post('/workspace/files/download-token', params={'agent_id': agent_id, 'session_id': session_id, 'path': str(tmp_path.parent)})
        assert token_denied.status_code == 403
        root_listing = alice.get('/workspace/directories', params={'agent_id': agent_id, 'session_id': session_id})
        assert root_listing.status_code == 200, root_listing.text
        assert agent_id in alice.get('/agent/').text
        assert agent_id not in bob.get('/agent/').text
        credential = alice.post('/credential/', json={'data': {'type': 'openai_credential', 'name': 'Isolated credential', 'api_key': 'fixture-only'}})
        assert credential.status_code == 201, credential.text
        credential_id = credential.json()['credential_id']
        assert credential_id not in bob.get('/credential/').text
        second = alice.post('/harbor/tenants', json={'name': 'Separate tenant'}).json()['id']
        assert agent_id not in alice.get('/agent/', headers={'X-Tenant-ID': second}).text
        assert credential_id not in alice.get('/credential/', headers={'X-Tenant-ID': second}).text
        assert alice.patch(f'/agent/{agent_id}', json={'name': 'hijacked'}, headers={'X-Tenant-ID': second}).status_code in (403, 404)
        assert bob.patch(f'/agent/{agent_id}', json={'name': 'hijacked'}).status_code in (403, 404)
        assert bob.get(f'/sessions/{session_id}/messages', params={'agent_id': agent_id}).status_code in (403, 404)
        assert bob.get('/agent/', headers={'X-Tenant-ID': a['active_tenant_id']}).status_code == 403
        cookie = alice.cookies.get('harbor_session')
    with TestClient(create_harbor_app(tmp_path)) as restarted:
        restarted.cookies.set('harbor_session', cookie)
        assert agent_id in restarted.get('/agent/').text
        assert session_id in restarted.get('/sessions/', params={'agent_id': agent_id}).text


def test_explicit_workspace_ids_cannot_share_across_owners(tmp_path):
    async def check():
        async with TenantWorkspaceManager(tmp_path) as manager:
            a = await manager.get_workspace('tenant_a_user', 'same_agent', 'a', 'same_workspace')
            b = await manager.get_workspace('tenant_b_user', 'same_agent', 'b', 'same_workspace')
            assert a.workdir != b.workdir
            assert a is not b
    asyncio.run(check())
