"""Real Chromium check of the two-origin MCP Apps relay; no external services."""
import json
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from playwright.sync_api import sync_playwright

from harbor.connectors.ui_sandbox import render_sandbox


def main():
    host_socket, sandbox_socket = socket.socket(), socket.socket()
    host_socket.bind(('127.0.0.1', 0))
    sandbox_socket.bind(('127.0.0.1', 0))
    host_url = f'http://127.0.0.1:{host_socket.getsockname()[1]}'
    sandbox_url = f'http://127.0.0.1:{sandbox_socket.getsockname()[1]}'
    app = FastAPI()
    network_hits = []
    inner = '''<!doctype html><html><body><input id="name" value="CRM opportunity">
<script>(async()=>{
 let domBlocked=false, cookieBlocked=false, networkBlocked=false;
 try { void top.document.body; } catch { domBlocked=true; }
 try { void document.cookie; } catch { cookieBlocked=true; }
 try { await fetch('__HOST__/forbidden'); } catch { networkBlocked=true; }
 parent.postMessage({jsonrpc:'2.0',method:'test/result',params:{domBlocked,cookieBlocked,networkBlocked}},'*');
 window.addEventListener('message',e=>{if(e.data?.method==='test/ping')parent.postMessage({jsonrpc:'2.0',id:e.data.id,result:'pong'},'*');});
})();</script></body></html>'''.replace('__HOST__', host_url)

    @app.get('/sandbox')
    def sandbox():
        return render_sandbox({})

    @app.get('/forbidden')
    def forbidden():
        network_hits.append(True)
        return {'unsafe': True}

    @app.get('/')
    def host():
        # Only the fixed relay receives same-origin permission. The app does not.
        return HTMLResponse('''<!doctype html><html><body><iframe id="app" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
<script>
 const frame=document.getElementById('app');window.results=[];
 window.addEventListener('message',event=>{
  if(event.source!==frame.contentWindow||event.origin!==__ORIGIN__)return;
  if(event.data?.method==='ui/notifications/sandbox-proxy-ready'){
   frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/sandbox-resource-ready',params:{html:__INNER__,sandbox:'allow-scripts allow-same-origin',csp:{connectDomains:['*']}}},__ORIGIN__);
  }else {window.results.push(event.data);}
 });
 frame.src=__URL__;
</script></body></html>'''.replace('__ORIGIN__', json.dumps(sandbox_url))
             .replace('__INNER__', json.dumps(inner).replace('</', '<\\/'))
             .replace('__URL__', json.dumps(sandbox_url + '/sandbox')))

    servers = [uvicorn.Server(uvicorn.Config(app, log_level='error')) for _ in range(2)]
    threads = [threading.Thread(target=lambda s=s, sock=sock: s.run(sockets=[sock]), daemon=True)
               for s, sock in zip(servers, [host_socket, sandbox_socket])]
    for thread in threads:
        thread.start()
    try:
        deadline = time.monotonic() + 15
        while not all(server.started for server in servers):
            assert time.monotonic() < deadline, 'Fixture server failed to start'
            time.sleep(.05)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            try:
                page = browser.new_page()
                page.goto(host_url)
                page.wait_for_function("window.results.some(x=>x.method==='test/result')")
                result = page.evaluate("window.results.find(x=>x.method==='test/result').params")
                assert result == dict(domBlocked=True, cookieBlocked=True, networkBlocked=True), result
                assert not network_hits, 'Connector bypassed HTTP CSP'
                page.evaluate("document.getElementById('app').contentWindow.postMessage({jsonrpc:'2.0',id:12,method:'test/ping'}, '*')")
                page.wait_for_function("window.results.some(x=>x.id===12&&x.result==='pong')")
            finally:
                browser.close()
    finally:
        for server in servers:
            server.should_exit = True
        for thread in threads:
            thread.join(timeout=5)
        host_socket.close()
        sandbox_socket.close()
    print('PASS: two-origin relay, DOM/cookie isolation, network CSP, ignored permission overrides, RPC round trip')


if __name__ == '__main__':
    main()
