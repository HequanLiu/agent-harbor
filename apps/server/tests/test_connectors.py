import io
import json
import zipfile
import pytest
from cryptography.fernet import Fernet
from harbor.connectors.package import read_package


def package(url='https://mes.example/mcp', extra=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('connector-meta.json', json.dumps({'source':'test-system','name':'Test','version':'1.0.0'}))
        z.writestr('mcp.json', json.dumps({'mcpServers':{'test': {'type':'streamableHttp','url':url, **(extra or {})}}}))
        z.writestr('icon.svg','<svg/>')
        z.writestr('skills/test-skill/SKILL.md','---\nname: test-skill\ndescription: Test connector\n---\nUse tools.')
    return b.getvalue()


def test_remote_only_package():
    assert read_package(package())['mcp']['url']=='https://mes.example/mcp'
    with pytest.raises(ValueError): read_package(package(extra={'command':'calc.exe'}))
    assert read_package(package(url='http://localhost:8086/mcp'))['mcp']['url']=='http://localhost:8086/mcp'


def test_encrypted_store_owner_boundary(tmp_path):
    from harbor.connectors.store import ConnectorStore
    key=Fernet.generate_key().decode()
    store=ConnectorStore(tmp_path/'connectors.sqlite3',key)
    item=store.install('tenant_a','alice',read_package(package()))
    assert store.list('tenant_a','bob')==[]
    with pytest.raises(KeyError): store.get('tenant_b','alice',item['id'])
    store.save_grant('tenant_a','alice',item['id'],{'access_token':'secret-access','refresh_token':'secret-refresh','expires_at':9999999999})
    assert store.grant('tenant_a','alice',item['id'])['access_token']=='secret-access'
    assert b'secret-access' not in (tmp_path/'connectors.sqlite3').read_bytes()
    assert 'access_token' not in str(store.list('tenant_a','alice'))
    restarted=ConnectorStore(tmp_path/'connectors.sqlite3',key)
    assert restarted.grant('tenant_a','alice',item['id'])['refresh_token']=='secret-refresh'
    restarted.disconnect('tenant_a','alice',item['id'])
    assert restarted.grant('tenant_a','alice',item['id']) is None

class FakeIdentity:
    def __init__(self): self.active=True; self.tenant='tenant_a'
    def authenticate(self,token):
        if not self.active: raise ValueError('Session revoked')
        assert token=='harbor-session'
        return {'tenant_id':self.tenant,'user_id':'alice'}
    def membership(self,user,tenant):
        if not self.active or (user,tenant)!=('alice','tenant_a'): raise ValueError('Membership revoked')


class FakeNetwork:
    def __init__(self): self.calls=[]; self.fail_revoke=False
    def check(self,url):
        assert url=='https://mes.example' or url.startswith('https://mes.example/'); return url
    async def json(self,method,url,**kwargs):
        self.calls.append((method,url,kwargs))
        if 'oauth-protected-resource' in url:
            return {'resource':'https://mes.example/mcp','authorization_servers':['https://mes.example'],'scopes_supported':['orders:read','orders:write']}
        if 'oauth-authorization-server' in url:
            return {'issuer':'https://mes.example','authorization_endpoint':'https://mes.example/authorize','token_endpoint':'https://mes.example/token','registration_endpoint':'https://mes.example/register','revocation_endpoint':'https://mes.example/revoke','code_challenge_methods_supported':['S256'],'token_endpoint_auth_methods_supported':['none']}
        if url.endswith('/register'): return {'client_id':'client-one','token_endpoint_auth_method':'none'}
        if url.endswith('/token'): return {'access_token':'oauth-access-secret','refresh_token':'oauth-refresh-secret','token_type':'Bearer','expires_in':3600,'scope':'orders:read orders:write'}
        if url.endswith('/revoke'):
            if self.fail_revoke: raise ValueError('Offline')
            return {}
        return {'id':'draft-one','revision':2}


def oauth_fixture(tmp_path):
    from harbor.connectors.store import ConnectorStore
    from harbor.connectors.oauth import ConnectorOAuth
    store=ConnectorStore(tmp_path/'connector.sqlite3',Fernet.generate_key())
    cid=store.install('tenant_a','alice',read_package(package()))['id']
    net=FakeNetwork(); identity=FakeIdentity()
    oauth=ConnectorOAuth(store,net,'https://harbor.example',identity)
    return store,cid,net,identity,oauth


def test_pkce_state_one_use_and_no_token_in_frontend(tmp_path):
    import asyncio
    from urllib.parse import urlsplit,parse_qs
    async def scenario():
        store,cid,net,identity,oauth=oauth_fixture(tmp_path)
        state,url=await oauth.start('tenant_a','alice',cid,'harbor-session')
        params=parse_qs(urlsplit(url).query)
        assert params['code_challenge_method']==['S256']
        assert 'code_verifier' not in params
        with pytest.raises(ValueError): await oauth.callback_exchange(state,'code','different-cookie')
        await oauth.callback_exchange(state,'code',state)
        assert await oauth.access('tenant_a','alice',cid)=='oauth-access-secret'
        assert 'oauth-access-secret' not in str(store.list('tenant_a','alice'))
        token_call=next(c for c in net.calls if c[1].endswith('/token'))
        import hashlib,base64
        challenge=base64.urlsafe_b64encode(hashlib.sha256(token_call[2]['data']['code_verifier'].encode()).digest()).rstrip(b'=').decode()
        assert params['code_challenge']==[challenge]
        with pytest.raises(ValueError): await oauth.callback_exchange(state,'code',state)
        assert b'oauth-access-secret' not in store.path.read_bytes()
    asyncio.run(scenario())


def test_callback_rechecks_harbor_session_and_tenant(tmp_path):
    import asyncio
    async def scenario():
        store,cid,net,identity,oauth=oauth_fixture(tmp_path)
        state,_=await oauth.start('tenant_a','alice',cid,'harbor-session')
        identity.tenant='tenant_b'
        with pytest.raises(ValueError): await oauth.callback_exchange(state,'code',state)
        assert store.grant('tenant_a','alice',cid) is None
    asyncio.run(scenario())


def test_disconnect_during_exchange_cannot_restore_grant(tmp_path):
    import asyncio
    async def scenario():
        store,cid,net,identity,oauth=oauth_fixture(tmp_path)
        state,_=await oauth.start('tenant_a','alice',cid,'harbor-session')
        original=net.json
        async def exchange(method,url,**kwargs):
            if url.endswith('/token'): store.disconnect('tenant_a','alice',cid)
            return await original(method,url,**kwargs)
        net.json=exchange
        with pytest.raises(ValueError): await oauth.callback_exchange(state,'code',state)
        assert store.grant('tenant_a','alice',cid) is None
        assert any(c[1].endswith('/revoke') for c in net.calls)
    asyncio.run(scenario())


def test_remote_revoke_failure_is_retryable_and_local_access_stops(tmp_path):
    import asyncio
    async def scenario():
        store,cid,net,identity,oauth=oauth_fixture(tmp_path)
        state,_=await oauth.start('tenant_a','alice',cid,'harbor-session')
        await oauth.callback_exchange(state,'code',state)
        net.fail_revoke=True
        assert await oauth.disconnect('tenant_a','alice',cid) is False
        with pytest.raises(ValueError): await oauth.access('tenant_a','alice',cid)
        assert store.revocations('tenant_a','alice',cid)
        net.fail_revoke=False
        assert await oauth.disconnect('tenant_a','alice',cid) is True
        assert not store.revocations('tenant_a','alice',cid)
    asyncio.run(scenario())


def test_refresh_rotates_once_for_concurrent_calls(tmp_path):
    import asyncio,time
    async def scenario():
        store,cid,net,identity,oauth=oauth_fixture(tmp_path)
        state,_=await oauth.start('tenant_a','alice',cid,'harbor-session')
        await oauth.callback_exchange(state,'code',state)
        grant=store.grant('tenant_a','alice',cid); grant['expires_at']=time.time()-1
        store.save_grant('tenant_a','alice',cid,grant)
        original=net.json
        async def delayed(method,url,**kwargs):
            if url.endswith('/token'): await asyncio.sleep(.05)
            return await original(method,url,**kwargs)
        net.json=delayed
        values=await asyncio.gather(oauth.access('tenant_a','alice',cid),oauth.access('tenant_a','alice',cid))
        assert values==['oauth-access-secret']*2
        assert len([c for c in net.calls if c[1].endswith('/token') and c[2]['data']['grant_type']=='refresh_token'])==1
    asyncio.run(scenario())


def test_ssrf_origin_and_public_dns_pinning(monkeypatch):
    import asyncio,socket
    from harbor.connectors.network import ConnectorNetwork,PublicNetworkBackend
    network=ConnectorNetwork(['https://mes.example'])
    for url in ['http://mes.example/mcp','https://other.example/mcp','https://user:pass@mes.example/mcp','https://mes.example/mcp?token=x']:
        with pytest.raises(ValueError): network.check(url)
    class Backend:
        async def connect_tcp(self,*args): return args[0]
    async def scenario():
        loop=asyncio.get_running_loop()
        async def private(*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        monkeypatch.setattr(loop,'getaddrinfo',private)
        with pytest.raises(ValueError): await PublicNetworkBackend(Backend()).connect_tcp('mes.example',443)
        async def public(*args,**kwargs): return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
        monkeypatch.setattr(loop,'getaddrinfo',public)
        assert await PublicNetworkBackend(Backend()).connect_tcp('mes.example',443)=='8.8.8.8'
    asyncio.run(scenario())


def test_sdk_config_does_not_serialize_grant_or_owner(tmp_path):
    from harbor.connectors.workspace import make_client
    store,cid,net,identity,oauth=oauth_fixture(tmp_path)
    client=make_client(oauth,net,'tenant_a','alice',cid)
    config=client.model_dump_json()
    assert 'Authorization' not in config and 'harbor-session' not in config and 'alice' not in config
    assert client.mcp_config.headers is None and not client.is_stateful


def test_package_rejects_nontext_metadata():
    raw=package(); output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(output,'w') as changed:
        for info in original.infolist():
            value=original.read(info)
            if info.filename=='connector-meta.json':
                meta=json.loads(value);meta['name']={'unsafe':'react-child'};value=json.dumps(meta)
            changed.writestr(info.filename,value)
    with pytest.raises(ValueError): read_package(output.getvalue())


def test_refresh_cannot_overwrite_newer_lease(tmp_path):
    store,cid,net,identity,oauth=oauth_fixture(tmp_path)
    store.save_grant('tenant_a','alice',cid,{'access_token':'old'})
    generation=store.grant('tenant_a','alice',cid)['_generation']
    lease1=store.claim_refresh('tenant_a','alice',cid,generation)
    with store.db() as db: db.execute('UPDATE connector_grants SET lease=0')
    lease2=store.claim_refresh('tenant_a','alice',cid,generation)
    assert lease1!=lease2
    store.release_refresh('tenant_a','alice',cid,generation,lease1)
    with pytest.raises(ValueError):
        store.save_grant('tenant_a','alice',cid,{'access_token':'stale'},expected_generation=generation,lease_owner=lease1)
    store.save_grant('tenant_a','alice',cid,{'access_token':'fresh'},expected_generation=generation,lease_owner=lease2)
    assert store.grant('tenant_a','alice',cid)['access_token']=='fresh'
    assert store.grant('tenant_a','alice',cid)['_generation']!=generation


def mes_package():
    raw=package();output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as original,zipfile.ZipFile(output,'w') as changed:
        for info in original.infolist():
            value=original.read(info);name=info.filename
            if name=='connector-meta.json':
                meta=json.loads(value);meta['source']='dresscode-mes';value=json.dumps(meta)
            if name.startswith('skills/'):
                name='skills/mes-order/SKILL.md';value=b'---\nname: mes-order\ndescription: Order workflow\n---\nUse order tools.'
            changed.writestr(name,value)
    return output.getvalue()


def api_fixture(tmp_path):
    from fastapi import FastAPI
    from harbor.auth import install_auth
    from harbor.connectors.api import install_connectors
    app=FastAPI()
    install_auth(app,tmp_path/'identity.sqlite3',allowed_origins={'https://harbor.example'})
    install_connectors(app,tmp_path,key=Fernet.generate_key().decode(),allowed_origins=['https://mes.example'],public_url='https://harbor.example',bridge_keys={'https://mes.example/mcp':'private-bridge-key'})
    return app


def signup(client,email):
    result=client.post('/harbor/auth/register',json={'email':email,'password':'correct-harbor-password','name':'Test','tenant_name':'Tenant'})
    assert result.status_code==201
    return result.json()


def connect_for(app,identity,cid):
    app.state.connector_store.save_grant(identity['active_tenant_id'],identity['user']['id'],cid,{
        'access_token':'private-oauth-token','refresh_token':'private-refresh-token','expires_at':9999999999,
        'client_id':'client-one','metadata':{'revocation_endpoint':'https://mes.example/revoke','token_endpoint':'https://mes.example/token'},'resource':'https://mes.example/mcp'})


def test_api_ownership_proxy_bridge_and_agui(tmp_path):
    from fastapi.testclient import TestClient
    app=api_fixture(tmp_path); calls=[]
    async def remote(method,url,**kwargs):
        calls.append((method,url,kwargs)); return {'draft_id':'draft-one','revision':1,'status':'editing','payload':{'mode':'create'}}
    app.state.connector_network.json=remote
    with TestClient(app) as alice,TestClient(app) as bob:
        identity=signup(alice,'alice@example.test');signup(bob,'bob@example.test')
        imported=alice.post('/harbor/connectors/import',content=mes_package(),headers={'Content-Type':'application/zip'})
        assert imported.status_code==201,imported.text
        cid=imported.json()['id'];connect_for(app,identity,cid)
        assert bob.get('/harbor/connectors/').json()['items']==[]
        assert bob.get(f'/harbor/connectors/{cid}/drafts/draft-one').status_code==404
        assert alice.post('/harbor/connectors/import',content=mes_package(),headers={'Content-Type':'application/zip','Origin':'https://evil.example'}).status_code==403
        assert alice.get(f'/harbor/connectors/{cid}/drafts/draft-one').status_code==200
        assert 'X-Harbor-Bridge-Key' not in calls[-1][2]['headers']
        confirmed=alice.post(f'/harbor/connectors/{cid}/drafts/draft-one/confirm',json={'revision':1,'content_hash':'hash'},headers={'X-Harbor-Bridge-Key':'forged'})
        assert confirmed.status_code==200
        assert calls[-1][2]['headers']=={'Authorization':'Bearer private-oauth-token','X-Harbor-Bridge-Key':'private-bridge-key'}
        assert 'private-' not in confirmed.text
        events=alice.get(f'/harbor/connectors/{cid}/drafts/draft-one/events')
        assert events.status_code==200 and events.headers['content-type'].startswith('text/event-stream')
        frame=json.loads(events.text.removeprefix('data: ').strip())
        assert frame=={'type':'STATE_SNAPSHOT','snapshot':{'draft':{'draft_id':'draft-one','revision':1,'status':'editing','payload':{'mode':'create'}}}}
        link=alice.get('/harbor/connectors/drafts/draft-one/connection')
        assert link.status_code==200 and link.json()['connector_id']==cid
        assert bob.get('/harbor/connectors/drafts/draft-one/connection').status_code==404
        reference=alice.get(f'/harbor/connectors/{cid}/references?kind=customer&q=Acme&page=2')
        assert reference.status_code==200 and calls[-1][2]['params']=={'kind':'customer','q':'Acme','page':2}
        uploaded=alice.post(f'/harbor/connectors/{cid}/sources',files={'file':('source.txt',b'order source','text/plain')})
        assert uploaded.status_code==200,uploaded.text
        assert calls[-1][2]['files']['file'][1]==b'order source'
        assert 'X-Harbor-Bridge-Key' not in calls[-1][2]['headers']
        assert alice.post(f'/harbor/connectors/{cid}/disconnect').json()['remote_revoked'] is True
        assert alice.get(f'/harbor/connectors/{cid}/drafts/draft-one').status_code==400


def test_workspace_filters_reserved_declarations_before_sdk_loader(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from harbor.connectors.workspace import ConnectorWorkspaces,PREFIX
    async def scenario():
        store,cid,net,identity,oauth=oauth_fixture(tmp_path)
        class Workspace:
            harbor_isolated_workspace=True
            async def add_mcp(self,*args,**kwargs):return None
            _mcp_lock=asyncio.Lock()
            _mcp_specs={('agent','session'):[SimpleNamespace(name=PREFIX+cid,is_stateful=True)]}
            _mcp_instances={}
            default_mcps=[SimpleNamespace(name=PREFIX+'evil',is_stateful=True)]
            async def list_mcps(self,**kwargs):
                assert not self._mcp_specs[('agent','session')]
                assert not self.default_mcps
                return []
        workspace=Workspace()
        ConnectorWorkspaces(store,oauth,net,tmp_path/'skills').wrap(workspace,'tenant_a','alice')
        assert await workspace.list_mcps(agent_id='agent',session_id='session')==[]
    asyncio.run(scenario())


def test_refresh_delete_race_queues_new_tokens_for_revocation(tmp_path):
    import asyncio,time
    async def scenario():
        store,cid,net,identity,oauth=oauth_fixture(tmp_path)
        state,_=await oauth.start('tenant_a','alice',cid,'harbor-session');await oauth.callback_exchange(state,'code',state)
        grant=store.grant('tenant_a','alice',cid);grant['expires_at']=time.time()-1;store.save_grant('tenant_a','alice',cid,grant)
        original=net.json
        async def delete_while_refreshing(method,url,**kwargs):
            if url.endswith('/token'): store.remove('tenant_a','alice',cid)
            return await original(method,url,**kwargs)
        net.json=delete_while_refreshing
        with pytest.raises(KeyError): await oauth.access('tenant_a','alice',cid)
        assert any(c[1].endswith('/revoke') for c in net.calls)
        assert store.grant('tenant_a','alice',cid) is None
    asyncio.run(scenario())


def test_source_parse_uses_installed_owner_and_draft_attachment_without_paid_run(tmp_path):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    app=api_fixture(tmp_path); calls=[]; contexts=[]
    async def resolve(owner,agent,session):
        contexts.append((owner,agent,session));return object()
    class Chat:
        def run(self,**kwargs):
            calls.append(kwargs)
            async def noop(): pass
            return noop()
    class Registry:
        def spawn(self,coro,**kwargs): coro.close()
    app.state.workspace_service=SimpleNamespace(resolve=resolve)
    app.state.chat_service=Chat();app.state.chat_run_registry=Registry()
    attached=True
    async def remote(method,url,**kwargs):
        if '/ui/sources/' in url: return {'asset_id':'asset-one'}
        return {'draft_id':'draft-one','revision':1,'status':'editing','payload':{'sources':[{'asset_id':'asset-one'}] if attached else []}}
    app.state.connector_network.json=remote
    with TestClient(app) as client:
        me=signup(client,'alice@example.test')
        cid=client.post('/harbor/connectors/import',content=mes_package(),headers={'Content-Type':'application/zip'}).json()['id']
        connect_for(app,me,cid)
        body={'draft_id':'draft-one','asset_id':'asset-one'}
        assert client.post(f'/harbor/connectors/{cid}/parse-source',json=body).status_code==409
        app.state.connector_store.bind(me['active_tenant_id'],me['user']['id'],cid,'agent-one','session-one')
        started=client.post(f'/harbor/connectors/{cid}/parse-source',json=body)
        assert started.status_code==200,started.text
        assert started.json()['url']=='/chat/agent-one/session-one?orderDraftId=draft-one'
        assert calls[0]['user_id']==f"{me['active_tenant_id']}_{me['user']['id']}"
        assert calls[0]['agent_id']=='agent-one' and 'private-' not in str(calls[0]['input_msg'])
        assert client.get(f'/harbor/connectors/{cid}/installations').json()['items']==[{'agent_id':'agent-one','session_id':'session-one'}]
        attached=False
        assert client.post(f'/harbor/connectors/{cid}/parse-source',json=body).status_code==409
        assert len(calls)==1


def test_connectors_require_sandbox_but_preserve_coding_tools(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from harbor.connectors.workspace import ConnectorWorkspaces,PREFIX
    async def scenario():
        store,cid,net,identity,oauth=oauth_fixture(tmp_path)
        manager=ConnectorWorkspaces(store,oauth,net,tmp_path/'skills')
        with pytest.raises(ValueError,match='isolated Docker'):
            manager.wrap(SimpleNamespace(),'tenant_a','alice')
        class Workspace:
            harbor_isolated_workspace=True
            _mcp_lock=asyncio.Lock()
            _mcp_specs={}
            _mcp_instances={}
            default_mcps=[]
            async def list_tools(self):return ['sandbox-bash','sandbox-read','sandbox-write']
            async def add_mcp(self,client,**kwargs):return client
            async def list_mcps(self,**kwargs):return [SimpleNamespace(name='sandbox-stdio')]
        workspace=manager.wrap(Workspace(),'tenant_a','alice')
        assert await workspace.list_tools()==['sandbox-bash','sandbox-read','sandbox-write']
        assert (await workspace.list_mcps(agent_id='agent',session_id='session'))[0].name=='sandbox-stdio'
        assert (await workspace.add_mcp(SimpleNamespace(name='ordinary'))).name=='ordinary'
        with pytest.raises(ValueError,match='Reserved'):
            await workspace.add_mcp(SimpleNamespace(name=PREFIX+cid))
    asyncio.run(scenario())


def test_explicit_local_http_network():
    from harbor.connectors.network import ConnectorNetwork, origin
    assert origin('http://localhost:8086/mcp') == 'http://localhost:8086'
    assert origin('http://localhost:80/mcp') == 'http://localhost'
    net = ConnectorNetwork(['http://localhost:8086'])
    assert net.check('http://localhost:8086/mcp')
    with pytest.raises(ValueError): net.check('http://localhost:9990/mcp')


def test_explicit_loopback_backend(monkeypatch):
    import asyncio, socket
    from harbor.connectors.network import PublicNetworkBackend
    class Backend:
        async def connect_tcp(self, host, *args): return host
    async def run():
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 8086))]
        monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', resolve)
        backend = PublicNetworkBackend(Backend(), allowed_loopback_hosts={'localhost'})
        assert await backend.connect_tcp('localhost', 8086) == '127.0.0.1'
        with pytest.raises(ValueError): await backend.connect_tcp('evil.example', 8086)
    asyncio.run(run())


def test_local_http_transport_ipv4_listener():
    import asyncio, threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from harbor.connectors.network import ConnectorNetwork
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')
        def log_message(self, *args): pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f'http://localhost:{server.server_port}'
    try:
        assert asyncio.run(ConnectorNetwork([url]).json('GET', url+'/mcp')) == {'ok': True}
    finally:
        server.shutdown(); server.server_close(); worker.join()
