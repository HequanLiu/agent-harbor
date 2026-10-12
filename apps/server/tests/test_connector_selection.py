import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from agentscope.app.message_bus import InMemoryMessageBus

from test_connectors import api_fixture, signup, connect_for, package
from harbor.connectors.package import read_package
from harbor.connectors.workspace import PREFIX


class Workspace:
    harbor_isolated_workspace = True
    def __init__(self):
        self._mcp_lock = asyncio.Lock()
        self._mcp_specs = {}
        self._mcp_instances = {}
        self.default_mcps = []
        self.skills = []
        self.fail = False
    async def list_mcps(self, **kwargs): return []
    async def add_mcp(self, client, **kwargs): return client
    async def list_skills(self, **kwargs): return self.skills
    async def add_skill(self, path, **kwargs):
        if self.fail: raise ValueError('Skill preparation failed')


def selection_fixture(tmp_path):
    app = api_fixture(tmp_path)
    workspace = Workspace()
    owners = set()
    calls = []
    async def get_session(owner, agent, session):
        return object() if owner in owners and agent == 'agent' and session in {'first', 'second'} else None
    async def resolve(owner, agent, session):
        assert await get_session(owner, agent, session) is not None
        calls.append(session)
        return workspace
    app.state.storage = SimpleNamespace(get_session=get_session)
    app.state.workspace_service = SimpleNamespace(resolve=resolve)
    app.state.message_bus = InMemoryMessageBus()
    return app, workspace, owners, calls


def add_connector(app, me, source, connected=True):
    pkg = deepcopy(read_package(package()))
    pkg['metadata']['source'] = source
    cid = app.state.connector_store.install(me['active_tenant_id'], me['user']['id'], pkg)['id']
    if connected: connect_for(app, me, cid)
    return cid


def test_session_selection_multiselect_deselect_and_tool_filtering(tmp_path):
    app, workspace, owners, calls = selection_fixture(tmp_path)
    with TestClient(app) as client:
        me = signup(client, 'alice@example.test')
        owners.add(me['active_tenant_id'] + '_' + me['user']['id'])
        one = add_connector(app, me, 'one')
        two = add_connector(app, me, 'two')
        url = '/harbor/connectors/sessions/agent/first'
        assert client.get(url).json() == {'connector_ids': []}
        assert not calls
        result = client.put(url, json={'connector_ids': [one, two]})
        assert result.status_code == 200, result.text
        assert set(result.json()['connector_ids']) == {one, two}
        assert client.get('/harbor/connectors/sessions/agent/second').json() == {'connector_ids': []}
        assert client.put(url, json={'connector_ids': [two]}).status_code == 200
        clients = asyncio.run(workspace.list_mcps(agent_id='agent', session_id='first'))
        assert [c.name for c in clients] == [PREFIX + two]
        assert len(calls) == 1  # Removing selections does not create a sandbox.
        assert client.put(url, json={'connector_ids': []}).json() == {'connector_ids': []}
        assert asyncio.run(workspace.list_mcps(agent_id='agent', session_id='first')) == []


def test_selection_failure_preserves_previous_bindings(tmp_path):
    app, workspace, owners, calls = selection_fixture(tmp_path)
    with TestClient(app) as client:
        me = signup(client, 'alice@example.test')
        owners.add(me['active_tenant_id'] + '_' + me['user']['id'])
        one = add_connector(app, me, 'one')
        two = add_connector(app, me, 'two')
        disconnected = add_connector(app, me, 'offline', connected=False)
        url = '/harbor/connectors/sessions/agent/first'
        assert client.put(url, json={'connector_ids': [one]}).status_code == 200
        for ids in [[disconnected], ['unknown'], [one, one]]:
            assert client.put(url, json={'connector_ids': ids}).status_code in (400, 404, 409, 422)
            assert client.get(url).json() == {'connector_ids': [one]}
        workspace.fail = True
        assert client.put(url, json={'connector_ids': [two]}).status_code == 400
        assert client.get(url).json() == {'connector_ids': [one]}


def test_selection_checks_session_and_connector_ownership(tmp_path):
    app, workspace, owners, calls = selection_fixture(tmp_path)
    with TestClient(app) as alice, TestClient(app) as bob:
        a = signup(alice, 'alice@example.test')
        b = signup(bob, 'bob@example.test')
        owners.add(a['active_tenant_id'] + '_' + a['user']['id'])
        cid = add_connector(app, a, 'one')
        url = '/harbor/connectors/sessions/agent/first'
        assert bob.get(url).status_code == 404
        assert bob.put(url, json={'connector_ids': [cid]}).status_code == 404
        owners.add(b['active_tenant_id'] + '_' + b['user']['id'])
        assert bob.put(url, json={'connector_ids': [cid]}).status_code == 404
        assert not calls
        assert alice.get('/harbor/connectors/sessions/agent/missing').status_code == 404


def test_store_replaces_bindings_atomically_and_checks_grants(tmp_path):
    app, workspace, owners, calls = selection_fixture(tmp_path)
    with TestClient(app) as client:
        me = signup(client, 'alice@example.test')
        one = add_connector(app, me, 'one')
        offline = add_connector(app, me, 'offline', connected=False)
        store = app.state.connector_store
        tenant, owner = me['active_tenant_id'], me['user']['id']
        store.replace_bindings(tenant, owner, 'agent', 'first', [one])
        with pytest.raises(ValueError):
            store.replace_bindings(tenant, owner, 'agent', 'first', [offline])
        assert store.bindings(tenant, owner, 'agent', 'first') == [one]
