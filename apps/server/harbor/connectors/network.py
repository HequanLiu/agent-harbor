"""HTTP(S) outbound transport with allowlisted origins and DNS pinning.

Addresses are validated at the actual TCP connect, not just before httpx does
another DNS lookup. TLS still verifies the original hostname through httpcore.
No environment proxies, redirects, private/link-local/reserved IPs or URL auth.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit
import httpx
from httpcore import ConnectError, ConnectTimeout
from httpcore._backends.auto import AutoBackend


def origin(url):
    try:
        p=urlsplit(url)
        if p.scheme not in {'http','https'} or not p.hostname or p.username or p.password or p.fragment or p.query:
            raise ValueError('Expected an HTTP or HTTPS URL without credentials, query or fragment')
        host=p.hostname.encode('idna').decode().lower()
        if '%' in host or '\\' in url or any(ord(c)<33 for c in url): raise ValueError('Invalid URL')
        authority = f'[{host}]' if ':' in host else host
        default_port = 443 if p.scheme == 'https' else 80
        return f'{p.scheme}://{authority}' + (f':{p.port}' if p.port not in (None,default_port) else '')
    except (UnicodeError,ValueError) as exc:
        raise ValueError('Invalid connector HTTP(S) URL') from exc


class PublicNetworkBackend:
    def __init__(self, backend=None, *, allowed_loopback_hosts=()):
        self.backend=backend or AutoBackend()
        self.allowed_loopback_hosts=set(allowed_loopback_hosts)
    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        records=await asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM)
        addresses=list(dict.fromkeys(r[4][0] for r in records))
        explicit_loopback = host in self.allowed_loopback_hosts
        if not addresses or any(not (ipaddress.ip_address(a).is_global or
                (explicit_loopback and ipaddress.ip_address(a).is_loopback)) for a in addresses):
            raise ValueError('Connector address resolves to a non-public network')
        for index, address in enumerate(addresses):
            try:
                return await self.backend.connect_tcp(address,port,timeout,local_address,socket_options)
            except (ConnectError, ConnectTimeout):
                if index == len(addresses)-1:
                    raise
    async def connect_unix_socket(self,*args,**kwargs): raise ValueError('Unix connector transports are forbidden')
    async def sleep(self,seconds): await asyncio.sleep(seconds)


class UpstreamFailure(ValueError):
    def __init__(self,status,payload):
        super().__init__(f'Connector request failed ({status})')
        self.status,self.payload=status,payload


class ConnectorNetwork:
    def __init__(self, allowed_origins):
        self.allowed={origin(v.strip()) for v in allowed_origins if v.strip()}
    def check(self,url):
        if origin(url) not in self.allowed: raise ValueError('Connector origin is not approved by the Harbor administrator')
        return url
    def client(self,timeout=30):
        transport=httpx.AsyncHTTPTransport(retries=0)
        transport._pool._network_backend=PublicNetworkBackend(allowed_loopback_hosts={
            urlsplit(value).hostname for value in self.allowed
            if urlsplit(value).hostname in {'localhost', '127.0.0.1', '::1'}})
        return httpx.AsyncClient(transport=transport,timeout=timeout,follow_redirects=False,trust_env=False)
    async def json(self,method,url,**kwargs):
        self.check(url)
        async with self.client() as client:
            async with client.stream(method,url,**kwargs) as response:
                data=bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>2*1024*1024: raise ValueError('Connector response exceeds limit')
                import json
                try: result=json.loads(data) if data else {}
                except ValueError:
                    if response.status_code>=300: raise UpstreamFailure(response.status_code,{}) from None
                    raise ValueError('Invalid connector response') from None
                if response.status_code>=300: raise UpstreamFailure(response.status_code,result)
                if not isinstance(result,(dict,list)): raise ValueError('Invalid connector response')
                return result
