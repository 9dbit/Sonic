"""Real ES256 WebAuthn signatures; all credentials and databases are synthetic."""
import copy
import hashlib
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from starlette.requests import Request
from webauthn.helpers.bytes_to_base64url import bytes_to_base64url as b64

from sonic import auth
from sonic.db import session_factory, utcnow
from sonic.passkeys import PasskeyChallenge, USER_ID

ORIGIN = "http://localhost"
HEADERS = {"Origin": ORIGIN}
SETUP = "synthetic-enrollment-key-" + "A" * 32


@pytest.fixture
def pc(client, monkeypatch):
    monkeypatch.setenv("SONIC_PASSWORDLESS_LOGIN", "true")
    monkeypatch.setenv("SONIC_PUBLIC_URL", ORIGIN)
    monkeypatch.setenv("SONIC_PASSKEY_ENROLLMENT_SHA256", auth.sha256(SETUP))
    monkeypatch.setenv("SONIC_PASSKEY_ENROLLMENT_EXPIRES", str(int(time.time()) + 3600))
    client.base_url = ORIGIN
    return client


def post(client, path, body=None, csrf=None):
    return client.post("/api/passkeys/" + path, json=body or {},
        headers={**HEADERS, **({"X-Sonic-CSRF": csrf} if csrf else {})})


def key():
    return ec.generate_private_key(ec.SECP256R1()), secrets.token_bytes(24)


def registration(start, private, cid, *, uv=True, origin=ORIGIN):
    numbers = private.public_key().public_numbers()
    cose = cbor2.dumps({1: 2, 3: -7, -1: 1,
        -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})
    client_data = json.dumps({"type": "webauthn.create", "challenge": start["options"]["challenge"],
        "origin": origin, "crossOrigin": False}).encode()
    flags = 0x45 if uv else 0x41
    data = hashlib.sha256(b"localhost").digest() + bytes([flags]) + bytes(4) + bytes(16)
    data += len(cid).to_bytes(2, "big") + cid + cose
    return {"id": b64(cid), "rawId": b64(cid), "type": "public-key", "response": {
        "clientDataJSON": b64(client_data),
        "attestationObject": b64(cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": data})),
        "transports": ["internal"]}, "clientExtensionResults": {}}


def assertion(start, private, cid, *, uv=True, origin=ORIGIN, challenge=None,
              rp="localhost", count=1, cross_origin=False):
    client_data = json.dumps({"type": "webauthn.get",
        "challenge": challenge or start["options"]["challenge"], "origin": origin,
        "crossOrigin": cross_origin}).encode()
    data = hashlib.sha256(rp.encode()).digest() + bytes([5 if uv else 1]) + count.to_bytes(4, "big")
    signature = private.sign(data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
    return {"id": b64(cid), "rawId": b64(cid), "type": "public-key", "response": {
        "clientDataJSON": b64(client_data), "authenticatorData": b64(data),
        "signature": b64(signature), "userHandle": b64(USER_ID)}, "clientExtensionResults": {}}


def enroll(client, *, initial=True, csrf=None):
    private, cid = key()
    authority = {"enrollment_key": SETUP} if initial else {}
    response = post(client, "register/options", authority, csrf)
    assert response.status_code == 200, response.text
    start = response.json()
    assert start["options"]["authenticatorSelection"]["residentKey"] == "required"
    assert start["options"]["authenticatorSelection"]["userVerification"] == "required"
    result = post(client, "register/verify", {**authority, "ceremony_id": start["ceremony_id"],
        "credential": registration(start, private, cid)}, csrf)
    assert result.status_code == 200, result.text
    return private, cid, result.json()


def test_setup_link_alone_cannot_read_or_control_anything(pc):
    start = post(pc, "register/options", {"enrollment_key": SETUP})
    assert start.status_code == 200
    assert pc.get("/api/session").json() == {"authenticated": False}
    for path in ("/api/history", "/api/memories", "/api/models", "/api/device/status", "/api/passkeys/manage"):
        assert pc.get(path).status_code == 401
    assert pc.post("/api/chat", json={"message": "hello"}).status_code == 401
    assert pc.post("/api/device/next").status_code == 401
    assert pc.post("/api/login", json={"token": "owner-test-token"}).status_code == 403


def test_enroll_without_owner_token_then_login_with_actual_signature(pc):
    private, cid, result = enroll(pc)
    assert result["authenticated"] and result["registered"]
    assert pc.get("/api/session").json()["authenticated"]
    assert post(pc, "register/options", {"enrollment_key": SETUP}).status_code == 403
    pc.cookies.clear()
    start = post(pc, "login/options").json()
    assert not start["options"].get("allowCredentials")
    assert start["options"]["userVerification"] == "required"
    result = post(pc, "login/verify", {"ceremony_id": start["ceremony_id"],
        "credential": assertion(start, private, cid)})
    assert result.status_code == 200, result.text
    assert "HttpOnly" in result.headers["set-cookie"]
    assert "SameSite=strict" in result.headers["set-cookie"]
    assert pc.get("/api/history").status_code == 200
    assert pc.post("/api/memories", json={"text": "synthetic memory"}).status_code == 403
    assert pc.post("/api/memories", json={"text": "synthetic memory"},
        headers={"X-Sonic-CSRF": result.json()["csrf"]}).status_code == 200


@pytest.mark.parametrize("change", [
    {"uv": False}, {"origin": "https://attacker.invalid"}, {"rp": "attacker.invalid"},
    {"challenge": b64(b"wrong-challenge")}, {"cross_origin": True},
])
def test_signed_assertions_with_wrong_security_properties_fail(pc, change):
    private, cid, _ = enroll(pc)
    pc.cookies.clear()
    start = post(pc, "login/options").json()
    result = post(pc, "login/verify", {"ceremony_id": start["ceremony_id"],
        "credential": assertion(start, private, cid, **change)})
    assert result.status_code in (400, 401), result.text
    assert not pc.get("/api/session").json()["authenticated"]


def test_invalid_signature_burns_challenge_and_cannot_retry_same_request(pc):
    private, cid, _ = enroll(pc)
    pc.cookies.clear()
    start = post(pc, "login/options").json()
    valid = assertion(start, private, cid)
    invalid = copy.deepcopy(valid)
    invalid["response"]["signature"] = b64(b"not-a-signature")
    assert post(pc, "login/verify", {"ceremony_id": start["ceremony_id"], "credential": invalid}).status_code == 401
    assert post(pc, "login/verify", {"ceremony_id": start["ceremony_id"], "credential": valid}).status_code == 401


def test_successful_signature_cannot_be_replayed(pc):
    private, cid, _ = enroll(pc)
    pc.cookies.clear()
    start = post(pc, "login/options").json()
    body = {"ceremony_id": start["ceremony_id"], "credential": assertion(start, private, cid)}
    assert post(pc, "login/verify", body).status_code == 200
    assert post(pc, "login/verify", body).status_code == 401


def test_login_is_bound_to_browser_cookie(pc):
    private, cid, _ = enroll(pc)
    pc.cookies.clear()
    start = post(pc, "login/options").json()
    body = {"ceremony_id": start["ceremony_id"], "credential": assertion(start, private, cid)}
    pc.cookies.clear()
    assert post(pc, "login/verify", body).status_code == 401


def test_registration_without_uv_fails(pc):
    private, cid = key()
    start = post(pc, "register/options", {"enrollment_key": SETUP}).json()
    result = post(pc, "register/verify", {"enrollment_key": SETUP,
        "ceremony_id": start["ceremony_id"], "credential": registration(start, private, cid, uv=False)})
    assert result.status_code == 400
    assert not pc.get("/api/passkeys/status").json()["enrolled"]


def test_expired_and_wrong_setup_links_fail(pc, monkeypatch):
    assert post(pc, "register/options", {"enrollment_key": "X" * 48}).status_code == 403
    monkeypatch.setenv("SONIC_PASSKEY_ENROLLMENT_EXPIRES", str(int(time.time()) - 1))
    assert post(pc, "register/options", {"enrollment_key": SETUP}).status_code == 403
    assert post(pc, "register/options", {}).status_code == 401


def test_missing_origin_and_cross_site_requests_fail(pc):
    assert pc.post("/api/passkeys/register/options", json={"enrollment_key": SETUP}).status_code == 403
    result = pc.post("/api/passkeys/register/options", json={"enrollment_key": SETUP},
        headers={"Origin": "https://attacker.invalid"})
    assert result.status_code == 403
    result = pc.post("/api/passkeys/register/options", json={"enrollment_key": SETUP},
        headers={**HEADERS, "Sec-Fetch-Site": "cross-site"})
    assert result.status_code == 403


def test_session_enrollment_requires_csrf_and_revocation_logs_out_every_session(pc):
    private, cid, first = enroll(pc)
    assert post(pc, "register/options").status_code == 403
    private2, cid2, _ = enroll(pc, initial=False, csrf=first["csrf"])
    headers = {**HEADERS, "X-Sonic-CSRF": first["csrf"]}
    deleted = pc.delete("/api/passkeys/" + b64(cid), headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert pc.get("/api/history").status_code == 401
    start = post(pc, "login/options").json()
    result = post(pc, "login/verify", {"ceremony_id": start["ceremony_id"],
        "credential": assertion(start, private2, cid2)})
    assert result.status_code == 200
    assert pc.delete("/api/passkeys/" + b64(cid2),
        headers={**HEADERS, "X-Sonic-CSRF": result.json()["csrf"]}).status_code == 409


def test_oversized_and_extra_fields_rejected(pc):
    assert post(pc, "register/options", {"enrollment_key": SETUP, "admin": True}).status_code == 422
    result = post(pc, "login/verify", {"ceremony_id": "A" * 30, "credential": {"large": "a" * 33000}})
    assert result.status_code == 422


def test_durable_rate_limit(pc):
    for _ in range(30):
        assert post(pc, "login/options").status_code == 409
    assert post(pc, "login/options").status_code == 429


def test_challenge_atomic_consumption_with_two_database_sessions(pc):
    from sonic.passkeys import _consume
    binding, cid = "B" * 43, "C" * 30
    with session_factory()() as db:
        db.add(PasskeyChallenge(id=cid, challenge=b64(b"one-challenge"), purpose="login",
            binding=auth.sha256(binding), authority="", expires_at=utcnow() + timedelta(seconds=120)))
        db.commit()
    def claim(_):
        req = Request({"type": "http", "headers": [(b"cookie", ("sonic_passkey_login=" + binding).encode())]})
        with session_factory()() as db:
            try:
                _consume(db, req, cid, "login", "")
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(claim, range(2))) == [200, 401]


def test_passwordless_html_and_public_metadata_do_not_expose_secrets(pc):
    html = pc.get("/").text
    assert 'id="passkeyLogin"' in html
    assert 'id="loginForm" hidden' in html
    assert 'id="ownerToken" type="password" autocomplete="off" disabled' in html
    assert "1.3.0" in html
    assert SETUP not in html
    assert "credential_id" not in pc.get("/api/passkeys/status").text
    assert SETUP not in pc.get("/api/passkeys/status").text


def test_open_preview_skips_login_without_granting_owner_access(client, monkeypatch):
    monkeypatch.setenv("SONIC_OPEN_PREVIEW", "true")
    monkeypatch.setenv("SONIC_PASSWORDLESS_LOGIN", "false")
    session = client.get("/api/session")
    assert session.status_code == 200
    body = session.json()
    assert body["authenticated"] is False
    assert body["preview"] is True
    assert body["capabilities"] == ["preview-ui"]
    assert "csrf" not in body
    html = client.get("/").text
    assert 'class="login-overlay hidden" id="loginOverlay"' in html
    assert 'id="passkeyLogin"' not in html
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/device/status").status_code == 401
    assert client.post("/api/chat", json={"message": "hello"}).status_code == 401
    assert client.post("/api/login", json={"token": "owner-test-token"}).status_code == 403
