"""Owner-only staging entry without changing anonymous preview semantics.

All requests use synthetic owner tokens, disposable local SQLite, and no
Windows, vendor AI, payment or external services.
"""
import json

import pytest


ORIGIN = "http://testserver"
LOGIN = {"Origin": ORIGIN, "X-Sonic-Owner-Entry": "1", "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def isolated_owner_flags(monkeypatch):
    monkeypatch.setenv("SONIC_PUBLIC_URL", ORIGIN)
    monkeypatch.setenv("SONIC_PASSWORDLESS_LOGIN", "false")
    monkeypatch.setenv("SONIC_OWNER_ENTRY_ENABLED", "false")
    monkeypatch.setenv("SONIC_OPEN_PREVIEW", "true")


def test_owner_entry_off_by_default_and_public_preview_unchanged(client):
    assert client.get("/owner").status_code == 404
    assert client.get("/owner.webmanifest").status_code == 404
    assert client.post("/api/owner/login", headers=LOGIN,
                       json={"token": "owner-test-token"}).status_code == 404
    public = client.get("/")
    assert public.status_code == 200
    assert '<div class="login-overlay hidden" id="loginOverlay">' in public.text
    session = client.get("/api/session").json()
    assert session["preview"] is True
    assert session["authenticated"] is False
    assert "csrf" not in session
    assert client.get("/api/history").status_code == 401


def test_owner_portal_is_separate_and_pwa_starts_in_owner_mode(client, monkeypatch):
    monkeypatch.setenv("SONIC_OWNER_ENTRY_ENABLED", "true")
    guest = client.get("/")
    assert '<div class="login-overlay hidden" id="loginOverlay">' in guest.text
    portal = client.get("/owner")
    assert portal.status_code == 200
    assert '<div class="login-overlay" id="loginOverlay">' in portal.text
    assert 'id="ownerToken"' in portal.text
    assert "sonic-black-grey-blue-v152.css" in portal.text
    assert "app.js?v=1.7.0" in portal.text
    assert 'href="/owner.webmanifest?v=1.7.0"' in portal.text
    assert portal.headers["cache-control"] == "no-store"
    assert portal.headers["x-robots-tag"] == "noindex, nofollow"
    assert "owner-test-token" not in portal.text
    manifest = client.get("/owner.webmanifest")
    assert manifest.status_code == 200
    data = manifest.json()
    assert data["start_url"] == data["id"] == "/owner"
    assert data["theme_color"] == "#050607"
    assert data["display"] == "standalone"
    assert all(icon["src"].startswith("/assets/") for icon in data["icons"])


def test_owner_token_restricted_to_private_same_origin_entry(client, monkeypatch):
    monkeypatch.setenv("SONIC_OWNER_ENTRY_ENABLED", "true")
    assert client.post("/api/login", json={"token": "owner-test-token"}).status_code == 403
    assert client.post("/api/owner/login", json={"token": "owner-test-token"}).status_code == 403
    assert client.post("/api/owner/login",
                       headers={"Origin": ORIGIN}, json={"token": "owner-test-token"}).status_code == 403
    assert client.post("/api/owner/login",
                       headers={**LOGIN, "Origin": "https://evil.example"},
                       json={"token": "owner-test-token"}).status_code == 403
    assert client.post("/api/owner/login", headers=LOGIN,
                       json={"token": "wrong-token"}).status_code == 401
    assert client.get("/api/session").json()["preview"] is True
    owner = client.post("/api/owner/login", headers=LOGIN,
                        json={"token": "owner-test-token"})
    assert owner.status_code == 200
    assert owner.json()["authenticated"] is True
    assert "set-cookie" in owner.headers
    assert "httponly" in owner.headers["set-cookie"].lower()
    assert "samesite=strict" in owner.headers["set-cookie"].lower()
    assert "max-age=" in owner.headers["set-cookie"].lower()
    session = client.get("/api/session").json()
    assert session["authenticated"] is True
    assert session["csrf"] == owner.json()["csrf"]
    assert not session.get("preview", False)
    assert client.get("/api/history").status_code == 200
    assert client.get("/api/local-ai/status").status_code == 200
    assert client.post("/api/local-ai/control", json={"action": "start"}).status_code == 403
    assert client.get("/api/preview/models").status_code == 200
    logout = client.post("/api/logout", headers={"X-Sonic-CSRF": session["csrf"]})
    assert logout.status_code == 200
    assert client.get("/api/session").json()["preview"] is True
    assert client.get("/api/history").status_code == 401


def test_forged_cookie_stays_guest_and_does_not_elevate(client, monkeypatch):
    monkeypatch.setenv("SONIC_OWNER_ENTRY_ENABLED", "true")
    client.cookies.set("sonic_session", "fake.signature")
    session = client.get("/api/session").json()
    assert session.get("preview") is True
    assert session["authenticated"] is False
    assert client.get("/api/local-ai/status").status_code == 401


def test_owner_portal_preserves_passwordless_future(client, monkeypatch):
    monkeypatch.setenv("SONIC_OWNER_ENTRY_ENABLED", "true")
    monkeypatch.setenv("SONIC_PASSWORDLESS_LOGIN", "true")
    portal = client.get("/owner")
    assert portal.status_code == 200
    assert 'id="passkeyLogin"' in portal.text
    assert 'id="ownerToken" type="password" autocomplete="off" disabled' in portal.text
    assert "/assets/passkey-login.js" in portal.text
    assert client.post("/api/owner/login", headers=LOGIN,
                       json={"token": "owner-test-token"}).status_code == 403
    assert client.get("/").status_code == 200
    assert '<div class="login-overlay hidden" id="loginOverlay">' in client.get("/").text


def test_owner_entry_rejected_outside_staging_even_if_flagged(client, monkeypatch):
    monkeypatch.setenv("SONIC_OWNER_ENTRY_ENABLED", "true")
    monkeypatch.setenv("SONIC_ENV", "production")
    assert client.get("/owner").status_code == 404
    assert client.post("/api/owner/login", headers=LOGIN,
                       json={"token": "owner-test-token"}).status_code == 404