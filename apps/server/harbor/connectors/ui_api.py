"""Generic MCP Apps sessions. No client-selected connector or network target."""
import json
import os
import time
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from . import ui_bridge
from .ui_store import UIStore


class OpenSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    binding_token: str = Field(min_length=32, max_length=128)
    agent_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approved: StrictBool


def install_ui(app, store, oauth, network, public_url, bridge_keys):
    ui = UIStore(store) if store else None
    app.state.connector_ui_store = ui
    app.state.connector_ui_bridge_keys = dict(bridge_keys or {})
    router = APIRouter(prefix='/harbor/connector-ui', tags=['Connector Apps'])

    def trust_key(value):
        key = app.state.connector_ui_bridge_keys.get(value['connector'])
        return key if isinstance(key, str) and key else None

    def owner(request):
        if ui is None: raise HTTPException(503, 'Connector Apps are not configured')
        p = request.state.principal
        app.state.identity_store.membership(p['user_id'], p['tenant_id'])
        return p['tenant_id'], p['user_id']

    async def check_chat(tenant, user, value):
        storage = getattr(app.state, 'storage', None)
        if storage is None or await storage.get_session(f'{tenant}_{user}', value['agent_id'], value['session_id']) is None:
            raise HTTPException(404, 'Chat session not found')

    async def lookup(request, sid):
        tenant, user = owner(request)
        try: value = ui.session(tenant, user, sid)
        except KeyError: raise HTTPException(404, 'UI session not found') from None
        except ValueError: raise HTTPException(403, 'Connector authorization or chat selection changed') from None
        await check_chat(tenant, user, value)
        return tenant, user, value

    async def tools_for(tenant, user, value):
        result = await ui_bridge.invoke(oauth, network, tenant, user, value['connector'], 'tools/list', {})
        disabled = store.get(tenant, user, value['connector'])['package']['mcp']['disabled_tools']
        return [ui_bridge.wire(t) for t in result.tools if t.name not in disabled]

    @router.post('/sessions')
    async def create(body: OpenSession, request: Request, response: Response):
        tenant, user = owner(request)
        try: value = ui.call(tenant, user, body.binding_token)
        except KeyError: raise HTTPException(404, 'Tool call association not found') from None
        except ValueError: raise HTTPException(403, 'Connector authorization or chat selection changed') from None
        if (value['agent_id'], value['session_id']) != (body.agent_id, body.session_id):
            raise HTTPException(404, 'Tool call does not belong to this chat')
        await check_chat(tenant, user, value)
        try: tools = await tools_for(tenant, user, value)
        except Exception: raise HTTPException(502, 'Connector tool discovery failed') from None
        # A resource is attached to the original executed tool, not browser input.
        sid = ui.put('session', tenant, user, value, ttl=1800)
        ticket = ui.put('sandbox', tenant, user, {'session': sid}, ttl=1800)
        response.headers['Cache-Control'] = 'no-store'
        return {'id': sid, 'resource_uri': value['resource_uri'], 'tool_name': value['tool_name'],
            'agent_id': value['agent_id'], 'session_id': value['session_id'],
            'tool_input': value['tool_input'], 'tool_result': value['tool_result'],
            'tools': [t for t in tools if ui_bridge.visible(t, 'app')],
            'sandbox_url': os.getenv('HARBOR_CONNECTOR_UI_SANDBOX_ORIGIN', public_url).rstrip('/') + '/harbor/connector-ui/sandbox/' + ticket}

    @router.get('/sandbox/{ticket}')
    async def sandbox(ticket: str):
        if ui is None: raise HTTPException(503, 'Connector Apps are not configured')
        try:
            tenant, user, value = ui.sandbox(ticket)
            app.state.identity_store.membership(user, tenant)
            await check_chat(tenant, user, value)
            resource = ui_bridge.wire(await ui_bridge.invoke(oauth, network, tenant, user, value['connector'], 'resources/read', {'uri': value['resource_uri']}))
            contents = resource.get('contents', [])
            content = next((c for c in contents if c.get('uri') == value['resource_uri'] and c.get('mimeType') == 'text/html;profile=mcp-app'), None)
            if content is None: raise ValueError('Invalid MCP App resource')
            from .ui_sandbox import render_sandbox
            return render_sandbox((content.get('_meta') or {}).get('ui', {}).get('csp'))
        except (KeyError, ValueError): raise HTTPException(403, 'Sandbox authorization expired or resource unavailable') from None

    @router.delete('/sessions/{sid}', status_code=204)
    async def close(sid: str, request: Request):
        tenant, user = owner(request)
        ui.delete('session', tenant, user, sid)
        return Response(status_code=204)

    @router.post('/sessions/{sid}/rpc')
    async def rpc(sid: str, request: Request, response: Response):
        from .api import bounded_body
        tenant, user, value = await lookup(request, sid)
        try: body = json.loads(await bounded_body(request, 384 * 1024))
        except ValueError: raise HTTPException(400, 'Invalid JSON-RPC') from None
        if not isinstance(body, dict) or body.get('jsonrpc') != '2.0' or not isinstance(body.get('id'), (int, str)):
            raise HTTPException(400, 'Expected a JSON-RPC request')
        method, params = body.get('method'), body.get('params', {})
        if not isinstance(params, dict): raise HTTPException(400, 'Invalid RPC parameters')
        if '_meta' in params and not isinstance(params['_meta'], dict): raise HTTPException(400, 'Invalid request metadata')
        # SDK requests may carry standard progress/context metadata. Credentials
        # and server routing never come from it; this host does not forward it.
        params = {key: item for key, item in params.items() if key != '_meta'}
        if method == 'resources/read':
            if set(params) != {'uri'} or params['uri'] != value['resource_uri']:
                raise HTTPException(403, 'Resource is not bound to this call')
        elif method == 'tools/call':
            if set(params) - {'name', 'arguments'} or not isinstance(params.get('arguments', {}), dict):
                raise HTTPException(400, 'Invalid tool call')
            try: tools = await tools_for(tenant, user, value)
            except Exception: raise HTTPException(502, 'Connector tool discovery failed') from None
            tool = next((t for t in tools if t['name'] == params.get('name') and ui_bridge.visible(t, 'app')), None)
            if tool is None: raise HTTPException(403, 'Tool is not available to this app')
            # Approval execution is never reachable through the untrusted UI RPC.
            execute_names = {(t.get('_meta') or {}).get('harbor/approval', {}).get('executeTool') for t in tools}
            if params['name'] in execute_names: raise HTTPException(403, 'Tool requires a native approval decision')
        else: raise HTTPException(403, 'Unsupported MCP App method')
        try:
            result = ui_bridge.wire(await ui_bridge.invoke(oauth, network, tenant, user, value['connector'], method, params))
        except Exception: raise HTTPException(502, 'Connector invocation failed; do not replay mutations automatically') from None
        response.headers['Cache-Control'] = 'no-store'
        envelope = {'jsonrpc': '2.0', 'id': body['id'], 'result': result}
        if method == 'tools/call' and not result.get('isError'):
            declaration = (tool.get('_meta') or {}).get('harbor/approval')
            if isinstance(declaration, dict) and declaration.get('prepareTool') == tool['name']:
                from .approvals import validate_challenge
                execute = declaration.get('executeTool')
                if not isinstance(execute, str) or not any(t['name'] == execute for t in tools):
                    raise HTTPException(502, 'Invalid approval tool declaration')
                if not trust_key(value): raise HTTPException(409, 'Connector approval trust is not configured')
                try: challenge = validate_challenge((result.get('structuredContent') or {}).get('approval'))
                except ValueError: raise HTTPException(502, 'Invalid connector approval challenge') from None
                aid = ui.put('approval', tenant, user, {'session': sid, 'value': value, 'execute': execute, 'challenge': challenge},
                    ttl=min(300, challenge['expires_at'] - time.time()))
                envelope['approval_required'] = {'id': aid, 'title': challenge['title'], 'summary': challenge['summary'], 'expires_at': challenge['expires_at']}
        return envelope

    @router.post('/approvals/{aid}/decision')
    async def decision(aid: str, body: Decision, request: Request, response: Response):
        from .approvals import receipt
        tenant, user = owner(request)
        try: pending = ui.get('approval', tenant, user, aid)
        except KeyError: raise HTTPException(404, 'Approval expired or already decided') from None
        _, _, value = await lookup(request, pending['session'])
        if value['connector'] != pending['value']['connector']: raise HTTPException(403, 'Approval association changed')
        key = trust_key(value)
        if not key: raise HTTPException(409, 'Connector approval trust is not configured')
        try: pending = ui.take('approval', tenant, user, aid)
        except KeyError: raise HTTPException(404, 'Approval expired or already decided') from None
        response.headers['Cache-Control'] = 'no-store'
        challenge = pending['challenge']
        def audit(outcome): ui.audit(aid, tenant, user, value['connector'], challenge['operation_id'], outcome)
        audit('approved' if body.approved else 'cancelled')
        if not body.approved: return {'cancelled': True}
        headers = {'X-Harbor-Approval': receipt(key, tenant, user, value['connector'], challenge), 'X-Harbor-Bridge-Key': key}
        try:
            result = ui_bridge.wire(await ui_bridge.invoke(oauth, network, tenant, user, value['connector'], 'tools/call',
                {'name': pending['execute'], 'arguments': challenge['arguments']}, headers=headers))
        except Exception:
            audit('unknown')
            raise HTTPException(502, 'Approval execution outcome is unknown; query the operation before retrying') from None
        audit('tool_error' if result.get('isError') else 'completed')
        return {'result': result}

    app.include_router(router)
