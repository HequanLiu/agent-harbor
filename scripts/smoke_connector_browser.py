"""Exercise the browser handoff with a real browser and a simulated OAuth provider."""
import asyncio
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/server'))
sys.path.insert(0,str(ROOT/'apps/server/tests'))
from harbor.auth import AuthBoundary
from harbor.connectors.api import install_connectors
from harbor.connectors.package import read_package
from test_connectors import FakeIdentity, FakeNetwork, package

with tempfile.TemporaryDirectory(prefix='harbor-browser-') as temp:
    sock=socket.socket()
    sock.bind(('127.0.0.1',0))
    base='http://127.0.0.1:'+str(sock.getsockname()[1])
    app=FastAPI()
    identity=FakeIdentity()
    app.state.identity_store=identity
    install_connectors(app,Path(temp),key=Fernet.generate_key(),
                       allowed_origins=['https://mes.example'],public_url=base)
    app.state.connector_oauth.network=FakeNetwork()
    store=app.state.connector_store
    cid=store.install('tenant_a','alice',read_package(package()))['id']
    app.add_middleware(AuthBoundary,store=identity,allowed_origins={'tauri://localhost'})
    with TestClient(app) as desktop:
        response=desktop.post('/harbor/connectors/'+cid+'/authorize?external_browser=true',
                              headers={'Authorization':'Bearer harbor-session'})
        assert response.status_code==200
        launch_url=response.json()['authorization_url']
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline,'Test server failed to start'
            time.sleep(.05)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context()
            page=context.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def consent(route):
                state=parse_qs(urlsplit(route.request.url).query)['state'][0]
                target=base+'/harbor/connectors/oauth/callback?state='+state+'&code=fixture-code'
                route.fulfill(content_type='text/html',body='<script>location.replace('+json.dumps(target)+')</script>')
            page.route('https://mes.example/authorize**',consent)
            page.goto(launch_url)
            expect(page.locator('h1')).to_have_text('连接已完成',timeout=15000)
            assert store.grant('tenant_a','alice',cid)
            assert not errors,errors
            page.goto(launch_url)
            expect(page.locator('#status')).to_contain_text('已过期',timeout=10000)
            browser.close()
        print('PASS: real Edge browser handoff, cookie, OAuth callback, and replay rejection')
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        sock.close()
