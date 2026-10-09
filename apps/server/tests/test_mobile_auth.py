from fastapi.testclient import TestClient
from test_auth import app, register


def mobile_login(client):
    response = client.post('/harbor/auth/mobile/login', json={
        'email': 'alice@example.test', 'password': 'correct-harbor-password',
    })
    assert response.status_code == 200, response.text
    assert 'set-cookie' not in response.headers
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['token_type'] == 'bearer'
    assert response.json()['expires_in'] == 86400
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_mobile_login_without_cookie_and_revoke(app):
    with TestClient(app) as client:
        me = register(client)
        headers = mobile_login(client)
        client.cookies.clear()
        assert client.get('/harbor/auth/me', headers=headers).json() == me
        probe = client.get('/identity-probe', headers={**headers, 'X-User-ID': 'victim'})
        assert probe.json()['owner'] == f"{me['active_tenant_id']}_{me['user']['id']}"
        assert client.post('/harbor/auth/logout', headers=headers).status_code == 204
        assert client.get('/identity-probe', headers=headers).status_code == 401


def test_invalid_bearer_never_falls_back_to_cookie(app):
    with TestClient(app) as client:
        register(client)
        for value in ['Bearer invalid', 'Bearer ', 'Basic invalid']:
            assert client.get('/identity-probe', headers={'Authorization': value}).status_code == 401
        assert client.get('/identity-probe').status_code == 200


def test_mobile_tenant_switch_and_isolation(app):
    with TestClient(app) as client, TestClient(app) as other:
        register(client)
        stranger = register(other, 'other@example.test')
        headers = mobile_login(client)
        client.cookies.clear()
        denied = client.get('/identity-probe', headers={**headers, 'X-Tenant-ID': stranger['active_tenant_id']})
        assert denied.status_code == 403
        tenant = client.post('/harbor/tenants', headers=headers, json={'name': 'Mobile'}).json()
        assert client.post('/harbor/auth/switch-tenant', headers=headers, json={'tenant_id': tenant['id']}).status_code == 200
        assert client.get('/harbor/auth/me', headers=headers).json()['active_tenant_id'] == tenant['id']


def test_mobile_wrong_password_and_cross_site_rejected(app):
    with TestClient(app) as client:
        register(client)
        data = {'email': 'alice@example.test', 'password': 'incorrect-password'}
        assert client.post('/harbor/auth/mobile/login', json=data).status_code == 401
        data['password'] = 'correct-harbor-password'
        assert client.post('/harbor/auth/mobile/login', json=data, headers={'Origin': 'https://attacker.example'}).status_code == 403


def test_mobile_cors_preflight_is_allowlisted(app):
    with TestClient(app) as client:
        headers = {'Origin': 'http://localhost:5177', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type,x-tenant-id'}
        response = client.options('/harbor/auth/mobile/login', headers=headers)
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == headers['Origin']
        headers['Origin'] = 'https://attacker.example'
        assert client.options('/harbor/auth/mobile/login', headers=headers).status_code == 400


def test_allowlisted_cross_site_mobile_login_and_bearer_writes(app):
    with TestClient(app) as client:
        register(client)
        browser = {'Origin': 'http://localhost:5177', 'Sec-Fetch-Site': 'cross-site'}
        data = {'email': 'alice@example.test', 'password': 'correct-harbor-password'}
        response = client.post('/harbor/auth/mobile/login', headers=browser, json=data)
        assert response.status_code == 200, response.text
        headers = {**browser, 'Authorization': 'Bearer ' + response.json()['access_token']}
        assert client.post('/harbor/tenants', headers=headers, json={'name': 'Mobile cross-site'}).status_code == 201
        assert client.post('/harbor/tenants', headers=browser, json={'name': 'Cookie blocked'}).status_code == 403
        assert client.post('/harbor/auth/login', headers=headers, json=data).status_code == 403
        assert client.post('/harbor/auth/register', headers=headers, json=data).status_code == 403
        assert client.post('/harbor/tenants', headers={**headers, 'Authorization': 'Bearer invalid'}, json={'name': 'Invalid token'}).status_code == 401
        assert client.post('/harbor/auth/logout', headers={**headers, 'Origin': 'https://attacker.example'}).status_code == 403
        assert client.post('/harbor/auth/logout', headers=headers).status_code == 204
