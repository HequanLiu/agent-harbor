from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from harbor.auth import install_auth


@pytest.mark.parametrize('origin', ['tauri://localhost', 'http://tauri.localhost', 'https://tauri.localhost'])
def test_native_origin_login_and_cookie_session(tmp_path, origin):
    app = FastAPI()
    install_auth(app, tmp_path/'identity.sqlite3', allowed_origins={origin})
    with TestClient(app) as client:
        registered = client.post('/harbor/auth/register', headers={'Origin': origin}, json={
            'email': 'desktop@example.test', 'password': 'desktop-test-password',
            'name': 'Desktop', 'tenant_name': 'Native workspace',
        })
        assert registered.status_code == 201
        assert client.get('/harbor/auth/me').status_code == 200
        assert client.post('/harbor/auth/logout', headers={'Origin': 'https://attacker.example'}).status_code == 403
        assert client.post('/harbor/auth/logout', headers={'Origin': origin}).status_code == 204
        assert client.get('/harbor/auth/me').status_code == 401
