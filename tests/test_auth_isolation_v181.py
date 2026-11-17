"""Server/asset contract for login isolation; layout is verified in real browsers."""
from sonic.api import VERSION


def test_private_login_is_locked_before_javascript(client, monkeypatch):
    monkeypatch.setenv('SONIC_OPEN_PREVIEW','true')
    monkeypatch.setenv('SONIC_OWNER_ENTRY_ENABLED','true')
    monkeypatch.setenv('SONIC_PASSWORDLESS_LOGIN','false')
    response=client.get('/owner')
    assert response.status_code==200
    assert 'orbit-v140 sonic-auth-locked' in response.text
    assert 'auth-isolation-v181.css' in response.text
    assert 'auth-isolation-v181.js' in response.text
    assert f'SONIC &middot; VERSION {VERSION}' in response.text
    assert 'VERSION 1.6.0' not in response.text
    assert '__SONIC_VERSION__' not in response.text
    assert client.get('/api/agent/memory').status_code==401
    assert client.get('/api/local-ai/status').status_code==401


def test_public_preview_is_not_locked(client, monkeypatch):
    monkeypatch.setenv('SONIC_OPEN_PREVIEW','true')
    response=client.get('/')
    assert response.status_code==200
    assert 'orbit-v140 sonic-auth-locked' not in response.text
    assert '<div class="login-overlay hidden" id="loginOverlay">' in response.text


def test_passkey_card_preserves_initial_isolation(client, monkeypatch):
    monkeypatch.setenv('SONIC_OPEN_PREVIEW','true')
    monkeypatch.setenv('SONIC_OWNER_ENTRY_ENABLED','true')
    monkeypatch.setenv('SONIC_PASSWORDLESS_LOGIN','true')
    response=client.get('/owner')
    assert response.status_code==200
    assert 'orbit-v140 sonic-auth-locked' in response.text
    assert 'id="passkeyLogin"' in response.text
    assert 'auth-isolation-v181.css' in response.text


def test_login_assets_fail_closed_without_hiding_public_preview(client):
    css=client.get('/assets/auth-isolation-v181.css').text
    js=client.get('/assets/auth-isolation-v181.js').text
    assert 'body.sonic-auth-locked' in css
    assert 'body:has(> #loginOverlay:not(.hidden))' in css
    assert 'display: none !important' in css
    assert 'element.inert=true' in js
    assert 'previous.clear()' in js
    assert "event.key!=='Tab'" in js
