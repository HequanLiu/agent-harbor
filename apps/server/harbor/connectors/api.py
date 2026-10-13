"""Same-origin connector management and narrow authenticated draft proxy."""
import json
import os
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import HTMLResponse
from .network import ConnectorNetwork
from .oauth import ConnectorOAuth
from .package import read_package
from .store import ConnectorStore
from .workspace import ConnectorWorkspaces, make_client

COOKIE='harbor_connector_oauth'


class SessionSelection(BaseModel):
    connector_ids: list[str]=Field(max_length=32)


class BrowserTicket(BaseModel):
    ticket: str=Field(min_length=1,max_length=200)


class InstallBody(BaseModel):
    model_config=ConfigDict(extra='forbid')
    agent_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,160}$')
    session_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,160}$')


async def bounded_body(request,limit):
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>limit: raise HTTPException(413,'Request exceeds size limit')
    return bytes(data)


def install_connectors(app,data_dir,workspace_manager=None,*,key=None,allowed_origins=None,public_url=None,bridge_keys=None):
    key=key if key is not None else os.getenv('HARBOR_CONNECTOR_TOKEN_KEY','')
    allowed_origins=allowed_origins if allowed_origins is not None else os.getenv('HARBOR_CONNECTOR_ALLOWED_ORIGINS','').split(',')
    public_url=public_url if public_url is not None else os.getenv('HARBOR_CONNECTOR_PUBLIC_URL','')
    bridge_keys=bridge_keys if bridge_keys is not None else json.loads(os.getenv('HARBOR_CONNECTOR_BRIDGE_KEYS','{}'))
    enabled=bool(key and any(allowed_origins) and public_url)
    store=oauth=network=workspaces=None
    if enabled:
        from ..formatter_safety import install_formatter_data_only_policy
        install_formatter_data_only_policy()
        store=ConnectorStore(Path(data_dir)/'connectors.sqlite3',key)
        network=ConnectorNetwork(allowed_origins)
        oauth=ConnectorOAuth(store,network,public_url,app.state.identity_store)
        workspaces=ConnectorWorkspaces(store,oauth,network,Path(data_dir)/'connector-skills',
            allow_trusted_local=bool(getattr(workspace_manager,'trusted_local',False)))
        if workspace_manager is not None: workspace_manager.connectors=workspaces
    app.state.connector_store=store
    app.state.connector_oauth=oauth
    app.state.connector_network=network
    router=APIRouter(prefix='/harbor/connectors',tags=['Connectors'])

    def owner(request):
        p=request.state.principal
        app.state.identity_store.membership(p['user_id'],p['tenant_id'])
        return p['tenant_id'],p['user_id']

    def ready():
        if not enabled: raise HTTPException(503,'Connector service requires a separate encryption key, approved origins and public callback URL')

    def row(request,cid):
        ready(); tenant,user=owner(request)
        try: return tenant,user,store.get(tenant,user,cid)
        except KeyError: raise HTTPException(404,'Connector not found') from None

    @router.get('/')
    def listing(request: Request):
        tenant,user=owner(request)
        return {'enabled':enabled,'items':store.list(tenant,user) if enabled else []}

    @router.post('/import',status_code=201)
    async def importing(request: Request):
        ready(); tenant,user=owner(request)
        if request.headers.get('content-type','').split(';')[0]!='application/zip': raise HTTPException(415,'Upload a ZIP package')
        raw=await bounded_body(request,5*1024*1024)
        try:
            package=read_package(raw); network.check(package['mcp']['url'])
            return store.install(tenant,user,package)
        except ValueError as exc: raise HTTPException(400,str(exc)) from None

    @router.post('/{cid}/authorize')
    async def authorize(cid: str,request: Request,response: Response,external_browser: bool=False):
        tenant,user,_=row(request,cid)
        if external_browser:
            try: url=await oauth.start_browser(tenant,user,cid,request.state.session_token)
            except ValueError as exc: raise HTTPException(400,str(exc)) from None
            response.headers['Cache-Control']='no-store'
            return {'authorization_url':url}
        try: state,url=await oauth.start(tenant,user,cid,request.state.session_token)
        except ValueError as exc: raise HTTPException(400,str(exc)) from None
        response.set_cookie(COOKIE,state,max_age=600,httponly=True,secure=oauth.secure_cookie,samesite='lax',path='/harbor/connectors/oauth/callback')
        response.headers['Cache-Control']='no-store'
        return {'authorization_url':url}

    @router.get('/oauth/browser')
    def browser_entry():
        ready()
        from .browser import browser_page
        return browser_page()

    @router.post('/oauth/browser')
    def browser_exchange(body: BrowserTicket,request: Request,response: Response):
        ready()
        expected=oauth.callback.split('/harbor/connectors/oauth/callback')[0]
        if request.headers.get('origin')!=expected:
            raise HTTPException(403,'Invalid browser origin')
        try: state,url=oauth.consume_browser(body.ticket)
        except (ValueError,KeyError,HTTPException):
            raise HTTPException(400,'Authorization link expired or already used; return to AgentHarbor and retry') from None
        response.set_cookie(COOKIE,state,max_age=600,httponly=True,secure=oauth.secure_cookie,samesite='lax',path='/harbor/connectors/oauth/callback')
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
        return {'authorization_url':url}

    @router.get('/oauth/callback')
    async def callback(request: Request):
        ready()
        try:
            await oauth.callback_exchange(request.query_params.get('state'),request.query_params.get('code'),request.cookies.get(COOKIE))
            response=HTMLResponse('<!doctype html><meta charset="utf-8"><title>连接完成</title><h1>连接已完成</h1><p>请关闭此窗口，返回 AgentHarbor。</p>')
        except (ValueError,KeyError,HTTPException):
            response=HTMLResponse('<!doctype html><meta charset="utf-8"><title>连接失败</title><h1>连接未完成</h1><p>授权已过期、取消或当前账号已改变。请返回 AgentHarbor 重新发起授权。</p>',status_code=400)
        response.delete_cookie(COOKIE,path='/harbor/connectors/oauth/callback',secure=oauth.secure_cookie,httponly=True,samesite='lax')
        response.headers['Cache-Control']='no-store'; response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
        return response

    @router.get('/{cid}/tools')
    async def discover_tools(cid: str,request: Request):
        tenant,user,_=row(request,cid)
        try:
            client=make_client(oauth,network,tenant,user,cid)
            tools=await client.list_raw_tools()
            result=[t.model_dump(mode='json',by_alias=True,exclude_none=True) for t in tools]
            store.tools(tenant,user,cid,result)
            return {'tools':result}
        except Exception: raise HTTPException(502,'Tool discovery failed; check connection and authorize again if expired') from None

    async def selection_owner(request,agent_id,session_id):
        ready()
        tenant,user=owner(request)
        if not all(re.fullmatch(r'[A-Za-z0-9_-]{1,160}',value) for value in (agent_id,session_id)):
            raise HTTPException(400,'Invalid session identity')
        record=await app.state.storage.get_session(f'{tenant}_{user}',agent_id,session_id)
        if record is None: raise HTTPException(404,'Session not found')
        return tenant,user

    def selected(tenant,user,agent_id,session_id):
        return {'connector_ids':sorted(cid for cid in store.bindings(tenant,user,agent_id,session_id)
                                       if store.grant(tenant,user,cid))}

    @router.get('/sessions/{agent_id}/{session_id}')
    async def session_connectors(agent_id: str,session_id: str,request: Request):
        tenant,user=await selection_owner(request,agent_id,session_id)
        return selected(tenant,user,agent_id,session_id)

    @router.put('/sessions/{agent_id}/{session_id}')
    async def select_connectors(agent_id: str,session_id: str,body: SessionSelection,request: Request):
        from agentscope.app.message_bus import MessageBusKeys
        tenant,user=await selection_owner(request,agent_id,session_id)
        ids=body.connector_ids
        if len(ids)!=len(set(ids)): raise HTTPException(400,'Duplicate connector selection')
        key=MessageBusKeys.session_lock(session_id)
        if await app.state.message_bus.is_locked(key):
            raise HTTPException(409,'请等待当前对话完成后再修改连接器')
        async with app.state.message_bus.acquire_lock(key,ttl_secs=MessageBusKeys.SESSION_RUN_TTL_SECS):
            for cid in ids:
                try: item=store.get(tenant,user,cid)
                except KeyError: raise HTTPException(404,'Connector not found') from None
                if not item['connected']: raise HTTPException(409,'连接器尚未授权，请先完成授权')
            current=set(store.bindings(tenant,user,agent_id,session_id))
            added=[cid for cid in ids if cid not in current]
            try:
                if added:
                    workspace=await app.state.workspace_service.resolve(f'{tenant}_{user}',agent_id,session_id)
                    for cid in added:
                        await workspaces.install(workspace,tenant,user,cid,agent_id,session_id,bind=False)
                store.replace_bindings(tenant,user,agent_id,session_id,ids)
            except ValueError as exc: raise HTTPException(400,str(exc)) from None
            return selected(tenant,user,agent_id,session_id)

    @router.post('/{cid}/install')
    async def install(cid: str,body: InstallBody,request: Request):
        tenant,user,_=row(request,cid)
        workspace=await app.state.workspace_service.resolve(f'{tenant}_{user}',body.agent_id,body.session_id)
        try: await workspaces.install(workspace,tenant,user,cid,body.agent_id,body.session_id)
        except ValueError as exc: raise HTTPException(400,str(exc)) from None
        return {'installed':True}


    @router.get('/{cid}/installations')
    async def installations(cid: str,request: Request):
        tenant,user,_=row(request,cid)
        available=[]
        for item in store.installations(tenant,user,cid):
            try: await app.state.workspace_service.resolve(f'{tenant}_{user}',item['agent_id'],item['session_id'])
            except HTTPException as exc:
                if exc.status_code in {403,404}: continue
                raise
            available.append(item)
        return {'items':available}

    @router.post('/{cid}/disconnect')
    async def disconnect(cid: str,request: Request):
        tenant,user,_=row(request,cid)
        revoked=await oauth.disconnect(tenant,user,cid)
        return {'status':'installed','remote_revoked':revoked}

    @router.delete('/{cid}',status_code=204)
    async def remove(cid: str,request: Request):
        tenant,user,_=row(request,cid)
        revoked=await oauth.disconnect(tenant,user,cid)
        if not revoked: raise HTTPException(502,'Local connection disabled; remote revocation could not be confirmed. Retry disconnect before removing.')
        store.remove(tenant,user,cid)
        return Response(status_code=204)

    from .legacy_mes import install_legacy_mes
    install_legacy_mes(router, app, store, oauth, network, bridge_keys, owner, ready, row, bounded_body)

    app.include_router(router)
    from .ui_api import install_ui
    install_ui(app,store,oauth,network,public_url,bridge_keys)
    return store
