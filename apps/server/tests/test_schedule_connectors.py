import asyncio
from types import SimpleNamespace as NS
import pytest
from cryptography.fernet import Fernet
from agentscope.app.storage import ScheduleOrigin, UserOrigin
from harbor.connectors.store import ConnectorStore
from harbor.connectors.workspace import ConnectorWorkspaces, PREFIX
from test_connectors import package
from harbor.connectors.package import read_package
from test_connector_selection import Workspace


def fixture(tmp_path):
    key=Fernet.generate_key()
    store=ConnectorStore(tmp_path/'connectors.sqlite3',key)
    store.test_key=key
    cid=store.install('tenant','owner',read_package(package()))['id']
    store.save_grant('tenant','owner',cid,{'access_token':'test','expires_at':9999999999})
    store.bind('tenant','owner',cid,'agent','source')
    async def access(*args): return 'test'
    manager=ConnectorWorkspaces(store,NS(access=access,store=store),None,tmp_path/'skills')
    async def get_session(user,agent,session):
        if user!='tenant_owner' or agent!='agent': return None
        if session=='source': return NS(origin=UserOrigin())
        if session.startswith('run'): return NS(origin=ScheduleOrigin(schedule_id='schedule'))
        return NS(origin=UserOrigin())
    async def get_schedule(user,sid):
        return NS(agent_id='agent',data=NS(source_session_id='source')) if user=='tenant_owner' and sid=='schedule' else None
    return store,cid,manager,NS(get_session=get_session,get_schedule=get_schedule)


def test_scheduled_sessions_inherit_tools_and_snapshot_survives_restart(tmp_path):
    store,cid,manager,storage=fixture(tmp_path)
    async def run():
        for session in ['run1','run2']:
            ws=Workspace()
            await manager.prepare_schedule(ws,storage,'tenant','owner','agent',session)
            assert store.bindings('tenant','owner','agent',session)==[cid]
            assert [c.name for c in await ws.list_mcps(agent_id='agent',session_id=session)]==[PREFIX+cid]
            store.replace_bindings('tenant','owner','agent','source',[])
        # Explicit deselection must not be undone on subsequent resolution.
        store.replace_bindings('tenant','owner','agent','run2',[])
        await manager.prepare_schedule(Workspace(),storage,'tenant','owner','agent','run2')
        assert store.bindings('tenant','owner','agent','run2')==[]
        # New manager/store, as after server restart, keeps the task snapshot.
        manager.store=ConnectorStore(store.path,store.test_key)
        await manager.prepare_schedule(Workspace(),storage,'tenant','owner','agent','run3')
        assert store.bindings('tenant','owner','agent','run3')==[cid]
    asyncio.run(run())


def test_schedule_inheritance_is_owner_agent_scoped_and_checks_revocation(tmp_path):
    store,cid,manager,storage=fixture(tmp_path)
    async def run():
        for owner,agent,session in [('other','agent','run1'),('owner','other','run1'),('owner','agent','ordinary')]:
            await manager.prepare_schedule(Workspace(),storage,'tenant',owner,agent,session)
            assert store.bindings('tenant',owner,agent,session)==[]
        await manager.prepare_schedule(Workspace(),storage,'tenant','owner','agent','run1')
        store.disconnect('tenant','owner',cid)
        with pytest.raises(ValueError,match='授权'):
            await manager.prepare_schedule(Workspace(),storage,'tenant','owner','agent','run1')
        with pytest.raises(ValueError,match='授权'):
            await manager.prepare_schedule(Workspace(),storage,'tenant','owner','agent','run2')
    asyncio.run(run())


@pytest.mark.parametrize('delete_via', ['api', 'tool', 'storage'])
def test_real_scheduler_creates_fresh_sessions_with_connector_tools(tmp_path, monkeypatch, delete_via):
    from functools import partial
    from fastapi.testclient import TestClient
    from harbor.app import create_harbor_app
    from test_connectors import signup, connect_for
    from agentscope.app.storage import ScheduleRecord, ScheduleData, ChatModelConfig
    from agentscope.app._manager._scheduler import SchedulerManager
    import agentscope.app._manager._scheduler._scheduler_manager as scheduler_module
    from datetime import datetime, timedelta

    monkeypatch.setenv('HARBOR_WORKSPACE_MODE','trusted_single_user_local')
    monkeypatch.setenv('HARBOR_CONNECTOR_TOKEN_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('HARBOR_CONNECTOR_ALLOWED_ORIGINS','https://mes.example')
    monkeypatch.setenv('HARBOR_CONNECTOR_PUBLIC_URL','https://harbor.example')
    monkeypatch.setenv('HARBOR_CONNECTOR_BRIDGE_KEYS','{}')
    deliveries=[]
    async def capture(bus, **kwargs): deliveries.append(kwargs)
    monkeypatch.setattr(scheduler_module,'deliver_to_inbox',capture)
    app=create_harbor_app(tmp_path)
    with TestClient(app) as client:
        me=signup(client,'scheduled@example.test')
        tenant,owner=me['active_tenant_id'],me['user']['id']
        user=tenant+'_'+owner
        agent=client.post('/agent/',json={'name':'Scheduled test'}).json()['agent_id']
        source=client.post('/sessions/',json={'agent_id':agent,'name':'Source'}).json()['session_id']
        cid=app.state.connector_store.install(tenant,owner,read_package(package()))['id']
        connect_for(app,me,cid)
        assert client.put(f'/harbor/connectors/sessions/{agent}/{source}',json={'connector_ids':[cid]}).status_code==200
        record=ScheduleRecord(user_id=user,agent_id=agent,data=ScheduleData(name='Mailbox check',source_session_id=source,
            cron_expression='0 0 1 1 *',started_at=datetime.now()+timedelta(days=365),stateful=False,
            chat_model_config=ChatModelConfig(type='test',credential_id='test',model='test',parameters={})))
        client.portal.call(app.state.storage.upsert_schedule,user,record)
        scheduler=SchedulerManager(app.state.storage,app.state.message_bus,app.state.workspace_manager,enabled=False)
        for _ in range(2):
            client.portal.call(scheduler._build_trigger(record))
            session=deliveries[-1]['session_id']
            ws=client.portal.call(app.state.workspace_service.resolve,user,agent,session)
            clients=client.portal.call(partial(ws.list_mcps,agent_id=agent,session_id=session))
            assert [c.name for c in clients]==[PREFIX+cid]
            assert 'test-skill' in [s.name for s in client.portal.call(partial(ws.list_skills,agent_id=agent))]
            assert client.get(f'/harbor/connectors/sessions/{agent}/{session}').json()['connector_ids']==[cid]
        assert deliveries[0]['session_id']!=deliveries[1]['session_id']

        from agentscope.message import Msg, TextBlock
        from agentscope.app._manager._scheduler._tools._schedule_delete import ScheduleDelete
        from unittest.mock import Mock
        history = Msg(name='assistant', role='assistant', content=[TextBlock(text='Preserved scheduled result')])
        client.portal.call(app.state.storage.upsert_message, user, session, history)
        url = f'/sessions/{session}/messages?agent_id={agent}'
        assert client.get(url).status_code == 200
        assert client.patch(f'/schedule/{record.id}', json={'enabled': False}).status_code == 200
        assert 'Preserved scheduled result' in client.get(url).text
        if delete_via == 'api':
            assert client.delete(f'/schedule/{record.id}').status_code == 204
        elif delete_via == 'tool':
            tool = ScheduleDelete(user, Mock(), app.state.storage, app.state.message_bus)
            client.portal.call(tool, record.id)
        else:
            assert client.portal.call(app.state.storage.delete_schedule, user, record.id)
        assert client.portal.call(app.state.storage.get_schedule, user, record.id) is None
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert 'Preserved scheduled result' in response.text
        assert client.get(f'/harbor/connectors/sessions/{agent}/{session}').json()['connector_ids'] == [cid]
        for delivery in deliveries:
            assert client.portal.call(app.state.storage.get_session, user, agent, delivery['session_id']) is not None
        assert client.delete(f'/sessions/{session}?agent_id={agent}').status_code == 204
        assert client.get(url).status_code == 404
