"""Standalone, secret-free HTTPS CONNECT proxy for isolated coding workers."""
import ipaddress
import os
import select
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def public_destination(host, port):
    if port != 443 or not host or '%' in host or any(ord(c)<33 for c in host):
        raise ValueError('Only public HTTPS destinations are allowed')
    denied={name.strip().lower() for name in os.getenv('HARBOR_PROXY_DENY_HOSTS','').split(',') if name.strip()}
    if host.lower() in denied:raise ValueError('Harbor service destination forbidden')
    blocked=set()
    for name in denied:
        try:blocked.update(r[4][0] for r in socket.getaddrinfo(name,443,type=socket.SOCK_STREAM))
        except OSError:raise ValueError('Cannot verify protected service address') from None
    addresses=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)))
    if any(address in blocked for address in addresses):raise ValueError('Harbor service destination forbidden')
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('Non-public destination forbidden')
    return addresses[0]


class Proxy(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args): pass
    def do_CONNECT(self):
        try:
            target=urlsplit('//'+self.path)
            if target.username or target.password or target.path or target.query or target.fragment:
                raise ValueError('Invalid destination')
            address=public_destination(target.hostname,target.port or 443)
            upstream=socket.create_connection((address,443),timeout=15)
        except (ValueError,OSError):
            self.send_error(403,'Destination is not allowed');return
        self.send_response(200,'Connection established');self.end_headers()
        self.connection.settimeout(60);upstream.settimeout(60)
        try:
            sockets=[self.connection,upstream]
            while True:
                readable,_,_=select.select(sockets,[],[],60)
                if not readable: break
                for source in readable:
                    data=source.recv(65536)
                    if not data:return
                    (upstream if source is self.connection else self.connection).sendall(data)
        except OSError: pass
        finally:upstream.close();self.close_connection=True
    def do_GET(self):self.send_error(403,'Use HTTPS CONNECT')
    do_POST=do_PUT=do_DELETE=do_GET


if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',3128),Proxy).serve_forever()
