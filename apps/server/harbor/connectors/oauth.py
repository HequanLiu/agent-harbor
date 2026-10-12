"""PKCE OAuth orchestration. Tokens never leave this service boundary."""
import asyncio
import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode, urlsplit
from .network import origin


class ConnectorOAuth:
    def __init__(self, store, network, public_url, identity_store):
        self.store,self.network,self.identity=store,network,identity_store
        p=urlsplit(public_url)
        if (p.scheme!='https' and not (p.scheme=='http' and p.hostname in {'localhost','127.0.0.1','::1'})) or p.path not in ('','/') or p.query or p.fragment or p.username:
            raise ValueError('HARBOR_CONNECTOR_PUBLIC_URL must be an HTTPS origin (loopback HTTP only for development)')
        self.callback=public_url.rstrip('/')+'/harbor/connectors/oauth/callback'
        self.secure_cookie=p.scheme=='https'

    async def discover(self,resource):
        self.network.check(resource)
        base=origin(resource)
        path=urlsplit(resource).path.rstrip('/')
        try:
            protected=await self.network.json('GET',base+'/.well-known/oauth-protected-resource'+path)
        except ValueError:
            protected=await self.network.json('GET',base+'/.well-known/oauth-protected-resource')
        if protected.get('resource','').rstrip('/')!=resource.rstrip('/'):
            raise ValueError('OAuth resource metadata does not match this connector')
        servers=protected.get('authorization_servers',[])
        if not isinstance(servers,list) or len(servers)!=1: raise ValueError('Connector must identify one authorization server')
        issuer=servers[0].rstrip('/')
        self.network.check(issuer)
        p=urlsplit(issuer)
        metadata_url=origin(issuer)+'/.well-known/oauth-authorization-server'+p.path.rstrip('/')
        meta=await self.network.json('GET',metadata_url)
        if meta.get('issuer','').rstrip('/')!=issuer: raise ValueError('Authorization issuer mismatch')
        for field in ('authorization_endpoint','token_endpoint','registration_endpoint','revocation_endpoint'):
            if not meta.get(field): raise ValueError('Connector OAuth must support registration and revocation')
            self.network.check(meta[field])
        if 'S256' not in meta.get('code_challenge_methods_supported',[]): raise ValueError('Connector OAuth requires PKCE S256')
        if 'none' not in meta.get('token_endpoint_auth_methods_supported',['none']): raise ValueError('Public OAuth clients are not supported')
        scopes=protected.get('scopes_supported') or meta.get('scopes_supported') or []
        if not isinstance(scopes,list) or len(scopes)>64 or any(not isinstance(x,str) or not x or len(x)>100 or ' ' in x for x in scopes): raise ValueError('Invalid OAuth scopes')
        return meta,scopes

    async def start(self,tenant,owner,cid,session_token):
        row=self.store.get(tenant,owner,cid); resource=row['package']['mcp']['url']
        meta,scopes=await self.discover(resource)
        registered=await self.network.json('POST',meta['registration_endpoint'],json={
            'client_name':'AgentHarbor','redirect_uris':[self.callback],
            'grant_types':['authorization_code','refresh_token'],'response_types':['code'],
            'token_endpoint_auth_method':'none','scope':' '.join(scopes)})
        client=registered.get('client_id')
        if not isinstance(client,str) or not client or len(client)>512 or registered.get('token_endpoint_auth_method','none')!='none': raise ValueError('Invalid public OAuth registration')
        state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        self.store.pending(hashlib.sha256(state.encode()).hexdigest(),{
            'tenant':tenant,'owner':owner,'connector':cid,'epoch':row['epoch'],'session_token':session_token,
            'resource':resource,'metadata':meta,'client_id':client,'verifier':verifier,'scopes':scopes})
        url=meta['authorization_endpoint']+'?'+urlencode({'client_id':client,'redirect_uri':self.callback,
            'response_type':'code','scope':' '.join(scopes),'state':state,'code_challenge':challenge,'code_challenge_method':'S256','resource':resource})
        return state,url

    async def start_browser(self,tenant,owner,cid,session_token):
        state,url=await self.start(tenant,owner,cid,session_token)
        ticket=secrets.token_urlsafe(32)
        self.store.pending('browser:'+hashlib.sha256(ticket.encode()).hexdigest(),{
            'tenant':tenant,'owner':owner,'connector':cid,'session_token':session_token,
            'state':state,'url':url,'epoch':self.store.get(tenant,owner,cid)['epoch']},ttl=60)
        return self.callback.rsplit('/',1)[0]+'/browser#'+ticket

    def consume_browser(self,ticket):
        if not ticket or len(ticket)>200: raise ValueError('Invalid browser authorization ticket')
        pending=self.store.consume_pending('browser:'+hashlib.sha256(ticket.encode()).hexdigest())
        principal=self.identity.authenticate(pending['session_token'])
        if (principal['tenant_id'],principal['user_id'])!=(pending['tenant'],pending['owner']):
            raise ValueError('Harbor account or tenant changed during authorization')
        self.identity.membership(pending['owner'],pending['tenant'])
        current=self.store.get(pending['tenant'],pending['owner'],pending['connector'])
        if current['epoch']!=pending['epoch']: raise ValueError('Authorization attempt was disconnected')
        return pending['state'],pending['url']

    async def callback_exchange(self,state,code,cookie):
        if not state or len(state)>200 or not cookie or not hmac.compare_digest(state,cookie): raise ValueError('Invalid OAuth browser state')
        pending=self.store.consume_pending(hashlib.sha256(state.encode()).hexdigest())
        principal=self.identity.authenticate(pending['session_token'])
        if (principal['tenant_id'],principal['user_id'])!=(pending['tenant'],pending['owner']): raise ValueError('Harbor account or tenant changed during authorization')
        self.identity.membership(pending['owner'],pending['tenant'])
        if not code or len(code)>2048: raise ValueError('Invalid authorization code')
        current=self.store.get(pending['tenant'],pending['owner'],pending['connector'])
        if current['epoch']!=pending['epoch']: raise ValueError('Authorization attempt was disconnected')
        tokens=await self.network.json('POST',pending['metadata']['token_endpoint'],data={
            'grant_type':'authorization_code','code':code,'client_id':pending['client_id'],
            'redirect_uri':self.callback,'code_verifier':pending['verifier'],'resource':pending['resource']})
        value=self.normalize(tokens,pending)
        try:
            self.store.save_grant(pending['tenant'],pending['owner'],pending['connector'],value,expected_epoch=pending['epoch'])
        except (ValueError,KeyError):
            self.store.queue_revocation(pending['tenant'],pending['owner'],pending['connector'],value)
            await self.revoke_value(value)
            raise
        return pending['connector']

    @staticmethod
    def normalize(tokens,context):
        access=tokens.get('access_token'); refresh=tokens.get('refresh_token') or context.get('refresh_token')
        expires=tokens.get('expires_in',3600)
        if (not isinstance(access,str) or not access or len(access)>16384 or any(ord(c)<33 or ord(c)>126 for c in access)
            or str(tokens.get('token_type','')).lower()!='bearer' or type(expires) is not int or not 0<expires<=30*86400
            or (refresh is not None and (not isinstance(refresh,str) or len(refresh)>16384))): raise ValueError('Invalid OAuth token response')
        return {'access_token':access,'refresh_token':refresh,'expires_at':time.time()+expires,
                'client_id':context['client_id'],'metadata':context['metadata'],'resource':context['resource'],
                'scopes':tokens.get('scope',' '.join(context.get('scopes',[]))).split()}

    async def access(self,tenant,owner,cid):
        # Enforce current membership even for already-built tool objects.
        self.identity.membership(owner,tenant)
        for _ in range(40):
            grant=self.store.grant(tenant,owner,cid)
            if not grant: raise ValueError('Connector is disconnected; authorize it again')
            if grant['expires_at']>time.time()+30: return grant['access_token']
            if not grant.get('refresh_token'): raise ValueError('Connector authorization expired; authorize it again')
            generation=grant['_generation']
            lease_owner=self.store.claim_refresh(tenant,owner,cid,generation)
            if not lease_owner:
                await asyncio.sleep(.2); continue
            try:
                # Re-read after the cross-process lease: another refresh might have just finished.
                current=self.store.grant(tenant,owner,cid)
                if not current or current['_generation']!=generation: raise ValueError('Connector was disconnected')
                if current['expires_at']>time.time()+30: return current['access_token']
                response=await asyncio.wait_for(self.network.json('POST',current['metadata']['token_endpoint'],data={
                    'grant_type':'refresh_token','refresh_token':current['refresh_token'],
                    'client_id':current['client_id'],'resource':current['resource']}),timeout=25)
                value=self.normalize(response,current)
                try: self.store.save_grant(tenant,owner,cid,value,expected_generation=generation,lease_owner=lease_owner)
                except (ValueError,KeyError):
                    self.store.queue_revocation(tenant,owner,cid,value)
                    await self.revoke_value(value); raise
                return value['access_token']
            except BaseException:
                self.store.invalidate_grant(tenant,owner,cid,generation)
                raise
            finally:
                self.store.release_refresh(tenant,owner,cid,generation,lease_owner)
        raise ValueError('Authorization refresh is busy; retry shortly')

    async def revoke_value(self,value):
        # Revoke both tokens; providers may revoke only the submitted token.
        success=True
        for token,hint in ((value.get('refresh_token'),'refresh_token'),(value.get('access_token'),'access_token')):
            if not token: continue
            try:
                await self.network.json('POST',value['metadata']['revocation_endpoint'],data={'token':token,'token_type_hint':hint,'client_id':value['client_id']})
            except Exception: success=False
        return success

    async def disconnect(self,tenant,owner,cid):
        self.store.disconnect(tenant,owner,cid)
        success=True
        for key,value in self.store.revocations(tenant,owner,cid):
            if await self.revoke_value(value): self.store.revoked(key)
            else: success=False
        return success
