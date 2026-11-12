"""Owner session cookies, CSRF enforcement and separately-scoped device tokens."""
from __future__ import annotations
import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from sqlalchemy import delete
from .db import OwnerSession, session_factory, utcnow
from collections import defaultdict
from fastapi import HTTPException, Request
from .config import setting, owner_ready, device_ready

COOKIE = "sonic_session"
SESSION_SECONDS = 8 * 60 * 60
_failures: dict[str, list[float]] = defaultdict(list)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_valid(token: str, expected_sha256: str) -> bool:
    if not token or len(token) > 512 or len(expected_sha256) != 64:
        return False
    return hmac.compare_digest(sha256(token), expected_sha256.lower())


def verify_login(token: str, remote_address: str) -> bool:
    if not owner_ready():
        raise HTTPException(status_code=503, detail="Owner credentials have not been configured")
    key = remote_address[:100]
    now = time.monotonic()
    recent = [t for t in _failures[key] if now - t < 600]
    _failures[key] = recent
    if len(recent) >= 5:
        raise HTTPException(status_code=429, detail="Too many login attempts")
    if not token_valid(token, setting("SONIC_OWNER_TOKEN_SHA256")):
        _failures[key].append(now)
        return False
    _failures.pop(key, None)
    return True


def _passkey_active(db, credential_id):
    from .passkeys import OwnerPasskey
    return (isinstance(credential_id, str) and 1 <= len(credential_id) <= 512
            and db.get(OwnerPasskey, credential_id) is not None)


def issue_session(*, passkey_id: str | None = None) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    data = {"exp": int(time.time()) + SESSION_SECONDS, "csrf": csrf, "sid": secrets.token_urlsafe(32)}
    if passkey_id is not None:
        data["passkey_id"] = passkey_id
    body = _b64(json.dumps(data, separators=(",", ":")).encode())
    mac = _b64(hmac.new(setting("SONIC_SESSION_SECRET").encode(), body.encode(), hashlib.sha256).digest())
    with session_factory()() as db:
        if passkey_id is not None and not _passkey_active(db, passkey_id):
            raise HTTPException(401, "Passkey was revoked; sign in again")
        db.execute(delete(OwnerSession).where(OwnerSession.expires_at <= utcnow()))
        db.add(OwnerSession(id=sha256(data["sid"]), expires_at=datetime.fromtimestamp(data["exp"], timezone.utc).replace(tzinfo=None)))
        db.commit()
    return body + "." + mac, csrf


def read_session(request: Request) -> dict:
    if not owner_ready():
        raise HTTPException(status_code=503, detail="Owner not configured")
    cookie = request.cookies.get(COOKIE, "")
    try:
        if len(cookie) > 2048:
            raise ValueError("invalid cookie")
        body, supplied_mac = cookie.split(".", 1)
        actual_mac = _b64(hmac.new(setting("SONIC_SESSION_SECRET").encode(),
                                   body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(actual_mac, supplied_mac):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
        if payload["exp"] <= time.time() or not isinstance(payload["csrf"], str):
            raise ValueError("expired")
        sid = payload.get("sid")
        if not isinstance(sid, str) or not 32 <= len(sid) <= 128:
            raise ValueError("invalid session")
        with session_factory()() as db:
            active = db.get(OwnerSession, sha256(sid))
            if active is None or active.expires_at <= utcnow():
                raise ValueError("revoked session")
            # Also closes a revocation/login race after signature verification:
            # a cookie associated with a removed passkey can never authorize use.
            if "passkey_id" in payload and not _passkey_active(db, payload["passkey_id"]):
                raise ValueError("revoked passkey")
        return payload
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        raise HTTPException(status_code=401, detail="Login required")


def require_owner(request: Request) -> dict:
    return read_session(request)


def require_owner_write(request: Request) -> dict:
    payload = read_session(request)
    received = request.headers.get("X-Sonic-CSRF", "")
    if not received or not hmac.compare_digest(received, payload["csrf"]):
        raise HTTPException(status_code=403, detail="CSRF token required")
    return payload


def require_device(request: Request) -> None:
    if not device_ready():
        raise HTTPException(status_code=503, detail="Device bridge not configured")
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer ") or not token_valid(
            authorization[7:].strip(), setting("SONIC_DEVICE_TOKEN_SHA256")):
        raise HTTPException(status_code=401, detail="Device authentication failed")


def revoke_session(payload: dict) -> None:
    """Persist revocation so logged-out cookies fail on every replica."""
    with session_factory()() as db:
        db.execute(delete(OwnerSession).where(OwnerSession.id == sha256(payload["sid"])))
        db.commit()
