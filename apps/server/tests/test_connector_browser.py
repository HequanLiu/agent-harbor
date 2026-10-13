import asyncio
from urllib.parse import urlsplit, parse_qs

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from harbor.auth import AuthBoundary
from harbor.connectors.api import install_connectors
from test_connectors import oauth_fixture, package
from harbor.connectors.package import read_package


def test_browser_handoff_one_use_bound_to_session(tmp_path):
    async def scenario():
        store, cid, net, identity, oauth = oauth_fixture(tmp_path)
        url = await oauth.start_browser('tenant_a', 'alice', cid, 'harbor-session')
        parts = urlsplit(url)
        assert parts.path == '/harbor/connectors/oauth/browser'
        assert not parts.query
        assert 'harbor-session' not in url
        ticket = parts.fragment
        state, target = oauth.consume_browser(ticket)
        assert parse_qs(urlsplit(target).query)['state'] == [state]
        with pytest.raises(ValueError):
            oauth.consume_browser(ticket)
        with pytest.raises(ValueError):
            await oauth.callback_exchange(state, 'code', None)
        await oauth.callback_exchange(state, 'code', state)
        assert store.grant('tenant_a', 'alice', cid)
    asyncio.run(scenario())


@pytest.mark.parametrize('invalidate', ['logout', 'tenant', 'disconnect', 'expire'])
def test_browser_handoff_rejects_invalidated_attempt(tmp_path, invalidate):
    async def scenario():
        store, cid, net, identity, oauth = oauth_fixture(tmp_path)
        url = await oauth.start_browser('tenant_a', 'alice', cid, 'harbor-session')
        if invalidate == 'logout':
            identity.active = False
        elif invalidate == 'tenant':
            identity.tenant = 'other'
        elif invalidate == 'disconnect':
            store.disconnect('tenant_a', 'alice', cid)
        else:
            with store.db() as db:
                db.execute('UPDATE connector_pending SET expires=0')
        with pytest.raises((ValueError, KeyError)):
            oauth.consume_browser(urlsplit(url).fragment)
    asyncio.run(scenario())


def test_browser_handoff_http_cookie_and_origin(tmp_path):
    store, cid, net, identity, oauth = oauth_fixture(tmp_path)
    app = FastAPI()
    app.state.identity_store = identity
    install_connectors(app, tmp_path / 'api', key=Fernet.generate_key(),
                       allowed_origins=['https://mes.example'], public_url='https://harbor.example')
    installed = app.state.connector_oauth
    installed.network = net
    store = app.state.connector_store
    cid = store.install('tenant_a', 'alice', read_package(package()))['id']
    app.add_middleware(AuthBoundary, store=identity, allowed_origins={'tauri://localhost'})
    with TestClient(app, base_url='https://harbor.example') as desktop:
        # Only an authenticated desktop can mint a ticket.
        response = desktop.post('/harbor/connectors/' + cid + '/authorize?external_browser=true',
                                headers={'Authorization': 'Bearer harbor-session'})
        assert response.status_code == 200
        ticket = urlsplit(response.json()['authorization_url']).fragment
    with TestClient(app, base_url='https://harbor.example') as browser:
        page = browser.get('/harbor/connectors/oauth/browser')
        assert page.status_code == 200
        assert 'location.hash' in page.text
        assert page.headers['Referrer-Policy'] == 'no-referrer'
        bad = browser.post('/harbor/connectors/oauth/browser', json={'ticket': ticket},
                           headers={'Origin': 'https://evil.example'})
        assert bad.status_code == 403
        missing = browser.post('/harbor/connectors/oauth/browser', json={'ticket': ticket})
        assert missing.status_code == 403
        response = browser.post('/harbor/connectors/oauth/browser', json={'ticket': ticket},
                                headers={'Origin': 'https://harbor.example'})
        assert response.status_code == 200
        state = parse_qs(urlsplit(response.json()['authorization_url']).query)['state'][0]
        cookie = response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie
        assert browser.post('/harbor/connectors/oauth/browser', json={'ticket': ticket},
                            headers={'Origin': 'https://harbor.example'}).status_code == 400
        callback = browser.get('/harbor/connectors/oauth/callback', params={'state': state, 'code': 'code'})
        assert callback.status_code == 200
        assert store.grant('tenant_a', 'alice', cid)
