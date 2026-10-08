from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from harbor.auth import install_auth


def build(path):
    app = FastAPI()
    install_auth(app, path, allowed_origins={'http://localhost:5177'})

    @app.get('/identity-probe')
    def probe(request: Request):
        return {'owner': request.headers.get('x-user-id')}

    return app


@pytest.fixture
def app(tmp_path):
    return build(tmp_path / 'identity.sqlite3')


def register(client, email='alice@example.test'):
    result = client.post('/harbor/auth/register', json={
        'email': email, 'password': 'correct-harbor-password', 'name': 'Alice',
        'tenant_name': 'First workspace',
    })
    assert result.status_code == 201, result.text
    return result.json()


def test_no_identity_header_can_bypass_login(app):
    with TestClient(app) as client:
        assert client.get('/identity-probe', headers={'X-User-ID': 'victim'}).status_code == 401


def test_registration_forged_identity_logout(app):
    with TestClient(app) as client:
        me = register(client)
        cookie = client.cookies.get('harbor_session')
        actual = client.get('/identity-probe', headers={'X-User-ID': 'victim'}).json()['owner']
        assert actual == f"{me['active_tenant_id']}_{me['user']['id']}"
        assert 'httponly' in client.post('/harbor/auth/login', json={
            'email': 'alice@example.test', 'password': 'correct-harbor-password',
        }).headers['set-cookie'].lower()
        assert client.post('/harbor/auth/logout').status_code == 204
        assert client.get('/identity-probe').status_code == 401
        client.cookies.set('harbor_session', cookie)
        # This earlier independent login session is revoked separately.
        client.post('/harbor/auth/logout')
        client.cookies.set('harbor_session', cookie)
        assert client.get('/identity-probe').status_code == 401


def test_password_duplicate_and_csrf(app):
    with TestClient(app) as client:
        register(client)
        assert client.post('/harbor/auth/register', json={
            'email': 'ALICE@example.test', 'password': 'correct-harbor-password',
            'name': 'Other', 'tenant_name': 'Other',
        }).status_code == 409
        assert client.post('/harbor/auth/login', json={
            'email': 'alice@example.test', 'password': 'incorrect-password',
        }).status_code == 401
        assert client.post('/harbor/tenants', json={'name': 'Bad'}, headers={
            'Origin': 'https://attacker.example',
        }).status_code == 403


def test_tenant_membership_namespace_and_revocation(app):
    with TestClient(app) as alice, TestClient(app) as bob:
        a = register(alice)
        b = register(bob, 'bob@example.test')
        tenant = a['active_tenant_id']
        url = f'/harbor/tenants/{tenant}/members'
        assert bob.get('/identity-probe', headers={'X-Tenant-ID': tenant}).status_code == 403
        assert bob.post(url, json={'email': 'bob@example.test'}).status_code == 403
        added = alice.post(url, json={'email': 'bob@example.test'})
        assert added.status_code == 201, added.text
        assert bob.get('/identity-probe', headers={'X-Tenant-ID': tenant}).status_code == 200
        assert alice.get('/identity-probe').json() != bob.get('/identity-probe', headers={'X-Tenant-ID': tenant}).json()
        assert bob.delete(f"{url}/{a['user']['id']}").status_code == 403
        assert alice.delete(f"{url}/{a['user']['id']}").status_code == 400
        assert alice.delete(f"{url}/{b['user']['id']}").status_code == 204
        assert bob.get('/identity-probe', headers={'X-Tenant-ID': tenant}).status_code == 403


def test_cookie_session_survives_app_restart(tmp_path):
    path = tmp_path / 'identities.sqlite3'
    with TestClient(build(path)) as client:
        register(client)
        cookie = client.cookies.get('harbor_session')
    with TestClient(build(path)) as restarted:
        restarted.cookies.set('harbor_session', cookie)
        assert restarted.get('/harbor/auth/me').status_code == 200


def test_switching_tenants_changes_server_namespace(app):
    with TestClient(app) as client:
        register(client)
        old_owner = client.get('/identity-probe').json()['owner']
        created = client.post('/harbor/tenants', json={'name': 'Second workspace'})
        assert created.status_code == 201
        assert client.post('/harbor/auth/switch-tenant', json={'tenant_id': created.json()['id']}).status_code == 200
        assert client.get('/identity-probe').json()['owner'] != old_owner


def test_download_token_cannot_override_authenticated_namespace(app):
    @app.get('/query-probe')
    def query_probe(request: Request):
        return dict(request.query_params)
    with TestClient(app) as client:
        register(client)
        assert client.get('/query-probe?token=other-tenant-token&path=file').json() == {'path': 'file'}


def test_expired_session_is_rejected(app):
    with TestClient(app) as client:
        register(client)
        with app.state.identity_store.db() as db:
            db.execute('UPDATE sessions SET expires=0')
        assert client.get('/identity-probe').status_code == 401


def test_registration_can_be_disabled(tmp_path):
    app = FastAPI()
    install_auth(app, tmp_path / 'id.sqlite3', allowed_origins=set(), registration_enabled=False)
    with TestClient(app) as client:
        assert client.get('/harbor/auth/status').json()['registration_enabled'] is False
        assert client.post('/harbor/auth/register', json={'email': 'test@example.test', 'password': 'long-enough-password', 'name': 'Test', 'tenant_name': 'Test'}).status_code == 403
