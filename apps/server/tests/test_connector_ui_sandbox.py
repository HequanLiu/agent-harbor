"""The public relay never trusts frame-provided sandbox or CSP permissions."""
import pytest


def test_sandbox_default_denies_network_and_uses_http_policy():
    from harbor.connectors.ui_sandbox import render_sandbox

    response = render_sandbox({})
    policy = response.headers['content-security-policy']
    assert "connect-src 'none'" in policy
    assert "object-src 'none'" in policy
    assert "base-uri 'none'" in policy
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'
    html = response.body.decode()
    assert 'ui/notifications/sandbox-proxy-ready' in html
    assert 'ui/notifications/sandbox-resource-ready' in html
    assert "event.source === window.parent" in html
    assert "event.source === frame.contentWindow" in html
    assert "allow-scripts allow-forms" in html
    assert 'params.sandbox' not in html
    assert 'params.csp' not in html


def test_sandbox_allows_only_declared_origins_and_blocks_script_injection():
    from harbor.connectors.ui_sandbox import render_sandbox

    response = render_sandbox({'connectDomains': ['https://uploads.example'],
                               'resourceDomains': ['https://cdn.example']})
    policy = response.headers['content-security-policy']
    assert 'connect-src https://uploads.example' in policy
    assert 'https://cdn.example' in policy
    assert 'https://uploads.example' in response.body.decode()


@pytest.mark.parametrize('domain', ["https://safe.example; script-src *", '*',
    'javascript:alert(1)', 'https://user:pass@example.com',
    'https://example.com/path', 'https://example.com?x=1',
    'https://example.com/#fragment', '</script><script>alert(1)</script>'])
def test_sandbox_rejects_invalid_csp_origins(domain):
    from harbor.connectors.ui_sandbox import render_sandbox

    with pytest.raises(ValueError):
        render_sandbox({'connectDomains': [domain]})


def test_only_well_formed_sandbox_get_reaches_ticket_validation_without_cookie():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from harbor.auth import AuthBoundary

    class Identity:
        def authenticate(self, token):
            from fastapi import HTTPException
            raise HTTPException(401, 'Authentication required')

    app = FastAPI()
    app.add_middleware(AuthBoundary, store=Identity(), allowed_origins=set())

    @app.get('/harbor/connector-ui/sandbox/{ticket}')
    def sandbox(ticket):
        # Real endpoint must validate ticket, grant and session before rendering.
        from fastapi import HTTPException
        raise HTTPException(404, 'Invalid sandbox ticket')

    with TestClient(app) as client:
        path = '/harbor/connector-ui/sandbox/' + 'a' * 43
        assert client.get(path).status_code == 404
        assert client.post(path).status_code == 401
        assert client.get('/harbor/connector-ui/sessions').status_code == 401
        assert client.get('/harbor/connector-ui/sandbox/short').status_code == 401
