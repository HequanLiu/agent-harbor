"""Same-origin cookie authentication and tenant boundary, without buffering SSE."""
from collections import defaultdict, deque
from pathlib import Path
import threading
import time
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from .identity import IdentityStore

COOKIE = 'harbor_session'


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        value = value.strip().lower()
        if value.count('@') != 1 or not all(value.split('@')):
            raise ValueError('请输入有效邮箱')
        return value


class Register(Login):
    name: str = Field(min_length=1, max_length=80)
    tenant_name: str = Field(min_length=1, max_length=80)

    @field_validator('name', 'tenant_name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('名称不能为空')
        return value.strip()


class TenantName(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=r'.*\S.*')


class TenantSelection(BaseModel):
    tenant_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class MemberInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class AuthBoundary:
    def __init__(self, app, store, allowed_origins):
        self.app, self.store, self.allowed_origins = app, store, allowed_origins

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
                return
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        try:
            path = scope['path']
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                origin = request.headers.get('origin')
                # Explicitly trusted mobile Web origins may use a separate API host.
                # Bearer requests never fall back to ambient cookies below. Keep
                # cookie login/register and all cookie-authenticated writes protected.
                mobile_request = path == '/harbor/auth/mobile/login' or (
                    path not in {'/harbor/auth/login', '/harbor/auth/register'}
                    and request.headers.get('authorization', '').lower().startswith('bearer ')
                )
                trusted_mobile = bool(origin and origin in self.allowed_origins and mobile_request)
                if (origin and origin not in self.allowed_origins) or (
                    request.headers.get('sec-fetch-site') == 'cross-site' and not trusted_mobile
                ):
                    raise HTTPException(403, '不允许来自此来源的请求')
            public = {
                ('GET', '/harbor/health'), ('GET', '/harbor/auth/status'),
                ('POST', '/harbor/auth/login'), ('POST', '/harbor/auth/register'),
                ('POST', '/harbor/auth/mobile/login'),
            }
            if (request.method, path) not in public:
                token = request.cookies.get(COOKIE, '')
                if 'authorization' in request.headers:
                    scheme, _, token = request.headers['authorization'].partition(' ')
                    if scheme.lower() != 'bearer' or not token or token != token.strip():
                        raise HTTPException(401, '登录会话无效，请重新登录')
                principal = await run_in_threadpool(self.store.authenticate, token)
                scope.setdefault('state', {})['session_token'] = token
                scope.setdefault('state', {})['principal'] = principal
                if not path.startswith('/harbor/'):
                    tenant_id = request.headers.get('x-tenant-id') or principal['tenant_id']
                    await run_in_threadpool(self.store.membership, principal['user_id'], tenant_id)
                    owner = f"{tenant_id}_{principal['user_id']}"
                    scope['headers'] = [(k, v) for k, v in scope['headers'] if k.lower() != b'x-user-id'] + [(b'x-user-id', owner.encode())]
                    # Upstream signed download links are bearer credentials. Require this
                    # logged-in owner instead, so a token cannot select another identity.
                    pairs = parse_qsl(scope.get('query_string', b'').decode(), keep_blank_values=True)
                    scope['query_string'] = urlencode([(k, v) for k, v in pairs if k != 'token']).encode()
                    if path == '/workspace/skill' and request.method == 'POST':
                        raise HTTPException(403, '请使用技能上传或技能库安装，不支持导入服务器目录')
                    if path in {'/workspace/directories', '/workspace/files', '/workspace/files/download-token'}:
                        params = dict(pairs)
                        agent_id, session_id = params.get('agent_id'), params.get('session_id')
                        if agent_id and session_id:
                            workspace = await request.app.state.workspace_service.resolve(owner, agent_id, session_id)
                            root = Path(workspace.workdir).resolve()
                            target = (root / params.get('path', '')).resolve()
                            if not target.is_relative_to(root):
                                raise HTTPException(403, '只能访问当前 Agent 的工作目录')
        except HTTPException as exc:
            await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def install_auth(app, database: Path, *, allowed_origins, registration_enabled=True, secure_cookie=False):
    store = IdentityStore(database)
    app.state.identity_store = store
    router = APIRouter(prefix='/harbor', tags=['AgentHarbor'])
    attempts = defaultdict(deque)
    lock = threading.Lock()

    def throttle(request):
        key = request.client.host if request.client else 'unknown'
        with lock:
            now = time.monotonic()
            for stale in [k for k, q in attempts.items() if not q or q[-1] < now - 60]:
                del attempts[stale]
            queue = attempts[key]
            while queue and queue[0] < now - 60:
                queue.popleft()
            if len(queue) >= 20:
                raise HTTPException(429, '操作过于频繁，请一分钟后重试')
            queue.append(now)

    def signed_in(response, user_id, tenant_id):
        token = store.new_session(user_id, tenant_id)
        response.set_cookie(COOKIE, token, max_age=86400, httponly=True, secure=secure_cookie, samesite='strict', path='/')
        return store.me(store.authenticate(token))

    @router.get('/health')
    def health():
        return {'status': 'ok', 'name': 'AgentHarbor', 'version': '0.1.0'}

    @router.get('/auth/status')
    def auth_status():
        return {'registration_enabled': registration_enabled}

    @router.post('/auth/register', status_code=201)
    def register(body: Register, request: Request, response: Response):
        if not registration_enabled:
            raise HTTPException(403, '当前服务已关闭自主注册')
        throttle(request)
        user_id, tenant_id = store.register(body.email, body.name, body.password, body.tenant_name)
        return signed_in(response, user_id, tenant_id)

    @router.post('/auth/login')
    def login(body: Login, request: Request, response: Response):
        throttle(request)
        return signed_in(response, *store.login(body.email, body.password))

    @router.post('/auth/mobile/login')
    def mobile_login(body: Login, request: Request, response: Response):
        throttle(request)
        token = store.new_session(*store.login(body.email, body.password))
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        return {'access_token': token, 'token_type': 'bearer', 'expires_in': 86400,
                'identity': store.me(store.authenticate(token))}

    @router.get('/auth/me')
    def me(request: Request):
        return store.me(request.state.principal)

    @router.post('/auth/logout', status_code=204)
    def logout(request: Request, response: Response):
        store.revoke(request.state.session_token)
        response.delete_cookie(COOKIE, path='/', secure=secure_cookie, httponly=True, samesite='strict')

    @router.post('/auth/switch-tenant')
    def switch(body: TenantSelection, request: Request):
        store.switch(request.state.session_token, request.state.principal['user_id'], body.tenant_id)
        return store.me(store.authenticate(request.state.session_token))

    @router.post('/tenants', status_code=201)
    def create_tenant(body: TenantName, request: Request):
        return store.create_tenant(request.state.principal['user_id'], body.name.strip())

    @router.get('/tenants/{tenant_id}/members')
    def members(tenant_id: str, request: Request):
        return store.members(request.state.principal['user_id'], tenant_id)

    @router.post('/tenants/{tenant_id}/members', status_code=201)
    def add_member(tenant_id: str, body: MemberInput, request: Request):
        store.add_member(request.state.principal['user_id'], tenant_id, body.email.strip())
        return {'status': 'added'}

    @router.delete('/tenants/{tenant_id}/members/{member_id}', status_code=204)
    def remove_member(tenant_id: str, member_id: str, request: Request):
        store.remove_member(request.state.principal['user_id'], tenant_id, member_id)

    app.include_router(router)
    app.add_middleware(AuthBoundary, store=store, allowed_origins=allowed_origins)
    app.add_middleware(CORSMiddleware, allow_origins=sorted(allowed_origins),
                       allow_credentials=True,
                       allow_methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
                       allow_headers=['Authorization', 'Content-Type', 'X-Tenant-ID'])
    return store
