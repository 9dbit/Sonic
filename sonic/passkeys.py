"""Single-owner passwordless access. No anonymous control-plane sessions.

Initial enrollment accepts an expiring, one-use operator-issued link, or an
existing owner session with CSRF. WebAuthn challenges are browser-bound and
atomically consumed in SQL. No biometric, private key or setup link is stored.
"""
from __future__ import annotations

import hmac
import json
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column
from webauthn import (base64url_to_bytes, generate_authentication_options,
                      generate_registration_options, options_to_json,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers.bytes_to_base64url import bytes_to_base64url
from webauthn.helpers.structs import (AttestationConveyancePreference,
    AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
    ResidentKeyRequirement, UserVerificationRequirement)

from . import auth
from .config import owner_ready, public_url, setting
from .db import Base, OwnerSession, get_db, utcnow

router = APIRouter(prefix="/api/passkeys")
TTL = 120
MAX_KEYS = 8
USER_ID = b"sonic-primary-owner-v1"


class OwnerPasskey(Base):
    __tablename__ = "owner_passkeys_v130"
    credential_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PasskeyChallenge(Base):
    __tablename__ = "owner_passkey_challenges_v130"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    challenge: Mapped[str] = mapped_column(String(160), nullable=False)
    purpose: Mapped[str] = mapped_column(String(12), nullable=False)
    binding: Mapped[str] = mapped_column(String(64), nullable=False)
    authority: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class PasskeyEnrollment(Base):
    __tablename__ = "owner_passkey_enrollments_v130"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class PasskeyGate(Base):
    __tablename__ = "owner_passkey_gate_v130"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PasskeyRate(Base):
    __tablename__ = "owner_passkey_rate_v130"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class EnrollmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enrollment_key: str | None = Field(default=None, min_length=32, max_length=128)


class Ceremony(EnrollmentBody):
    ceremony_id: str = Field(min_length=20, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    credential: dict

    @field_validator("credential")
    @classmethod
    def bounded(cls, value):
        if len(json.dumps(value).encode("utf-8")) > 32768:
            raise ValueError("Credential too large")
        return value


def enabled() -> bool:
    return setting("SONIC_PASSWORDLESS_LOGIN", "false").lower() == "true"


def _rp() -> tuple[str, str]:
    u = urlsplit(public_url())
    if not u.hostname or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
        raise HTTPException(503, "SONIC_PUBLIC_URL must be a canonical origin")
    local = (u.scheme == "http" and u.hostname == "localhost" and
             setting("SONIC_ENV", "local").lower() == "local" and
             not setting("RAILWAY_ENVIRONMENT_NAME"))
    if u.scheme != "https" and not local:
        raise HTTPException(503, "Passkeys require HTTPS")
    return u.hostname, f"{u.scheme}://{u.netloc}"


def _guard(request: Request):
    if not enabled() or not owner_ready():
        raise HTTPException(503, "Passwordless login is not configured")
    _, origin = _rp()
    if request.headers.get("origin") != origin:
        raise HTTPException(403, "Same-origin request required")
    if request.headers.get("sec-fetch-site") not in (None, "same-origin"):
        raise HTTPException(403, "Same-origin request required")
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, "JSON request required")


def _insert(db: Session, model):
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif db.bind.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise HTTPException(503, "Unsupported durable storage")
    return insert(model)


def _rate(db: Session, request: Request, purpose: str):
    now = utcnow()
    bucket = int(time.time()) // 300
    # Do not trust caller-supplied X-Forwarded-For as a rate-limit identity.
    address = request.client.host if request.client else "unknown"
    db.execute(delete(PasskeyRate).where(PasskeyRate.expires_at <= now))
    for subject, limit in ((address, 30), ("global", 150)):
        key = auth.sha256(f"{purpose}|{bucket}|{subject}")
        stmt = _insert(db, PasskeyRate).values(
            id=key, count=1, expires_at=now + timedelta(minutes=6))
        count = db.scalar(stmt.on_conflict_do_update(
            index_elements=[PasskeyRate.id], set_={"count": PasskeyRate.count + 1}
        ).returning(PasskeyRate.count))
        if count > limit:
            db.commit()
            raise HTTPException(429, "Too many attempts. Try again in five minutes.")
    db.commit()


def _cookie(purpose: str) -> str:
    return "sonic_passkey_" + purpose


def _new(db: Session, response: Response, purpose: str, authority: str, challenge: bytes) -> str:
    db.execute(delete(PasskeyChallenge).where(PasskeyChallenge.expires_at <= utcnow()))
    cid, binding = secrets.token_urlsafe(30), secrets.token_urlsafe(32)
    db.add(PasskeyChallenge(id=cid, challenge=bytes_to_base64url(challenge),
        purpose=purpose, binding=auth.sha256(binding), authority=authority,
        expires_at=utcnow() + timedelta(seconds=TTL)))
    db.commit()
    response.set_cookie(_cookie(purpose), binding, httponly=True, samesite="strict",
        secure=public_url().startswith("https://"), path="/api/passkeys", max_age=TTL)
    return cid


def _consume(db: Session, request: Request, cid: str, purpose: str, authority: str) -> bytes:
    binding = request.cookies.get(_cookie(purpose), "")
    if not 32 <= len(binding) <= 128:
        raise HTTPException(401, "Start verification again on this browser")
    value = db.scalar(delete(PasskeyChallenge).where(
        PasskeyChallenge.id == cid, PasskeyChallenge.purpose == purpose,
        PasskeyChallenge.binding == auth.sha256(binding),
        PasskeyChallenge.authority == authority,
        PasskeyChallenge.expires_at > utcnow()).returning(PasskeyChallenge.challenge))
    db.commit()
    if value is None:
        raise HTTPException(401, "Verification expired or already used")
    return base64url_to_bytes(value)


def _authority(request: Request, db: Session, enrollment_key: str | None) -> str:
    if enrollment_key is None:
        owner = auth.require_owner_write(request)
        return "owner:" + auth.sha256(owner["sid"])
    digest = auth.sha256(enrollment_key)
    expected = setting("SONIC_PASSKEY_ENROLLMENT_SHA256").lower()
    try:
        deadline = int(setting("SONIC_PASSKEY_ENROLLMENT_EXPIRES", "0"))
    except ValueError:
        deadline = 0
    if (len(expected) != 64 or not hmac.compare_digest(digest, expected) or
            deadline <= time.time() or deadline > time.time() + 86400 or
            db.get(PasskeyEnrollment, digest) is not None or
            db.scalar(select(OwnerPasskey.credential_id).limit(1)) is not None):
        raise HTTPException(403, "Enrollment link is invalid, expired, or already used")
    return "setup:" + digest


def _cross_origin(credential: dict):
    try:
        data = json.loads(base64url_to_bytes(credential["response"]["clientDataJSON"]))
        if not isinstance(data, dict) or data.get("crossOrigin", False) is not False:
            raise ValueError("Cross-origin ceremony")
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "Invalid browser verification") from None


def _session(response: Response, credential_id: str):
    session, csrf = auth.issue_session(passkey_id=credential_id)
    response.set_cookie(auth.COOKIE, session, httponly=True, samesite="strict",
        secure=public_url().startswith("https://"), max_age=auth.SESSION_SECONDS, path="/")
    return {"authenticated": True, "csrf": csrf}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    has_key = db.scalar(select(OwnerPasskey.credential_id).limit(1)) is not None
    return {"enabled": enabled(), "enrolled": has_key,
            "setup_required": enabled() and not has_key}


@router.post("/register/options")
def register_options(payload: EnrollmentBody, request: Request, response: Response,
                     db: Session = Depends(get_db)):
    _guard(request)
    _rate(db, request, "register")
    authority = _authority(request, db, payload.enrollment_key)
    rows = list(db.scalars(select(OwnerPasskey.credential_id)))
    if len(rows) >= MAX_KEYS:
        raise HTTPException(409, "At most eight passkeys may be registered")
    rp_id, _ = _rp()
    options = generate_registration_options(rp_id=rp_id, rp_name="SONIC",
        user_id=USER_ID, user_name="sonic-owner", user_display_name="SONIC Owner",
        attestation=AttestationConveyancePreference.NONE,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(x)) for x in rows],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED), timeout=TTL * 1000)
    cid = _new(db, response, "register", authority, options.challenge)
    return {"ceremony_id": cid, "options": json.loads(options_to_json(options))}


@router.post("/register/verify")
def register_verify(payload: Ceremony, request: Request, response: Response,
                    db: Session = Depends(get_db)):
    _guard(request)
    authority = _authority(request, db, payload.enrollment_key)
    challenge = _consume(db, request, payload.ceremony_id, "register", authority)
    _cross_origin(payload.credential)
    rp_id, origin = _rp()
    try:
        result = verify_registration_response(credential=payload.credential,
            expected_challenge=challenge, expected_origin=origin, expected_rp_id=rp_id,
            require_user_verification=True)
    except Exception:
        raise HTTPException(400, "Passkey registration could not be verified") from None
    credential_id = bytes_to_base64url(result.credential_id)
    if len(credential_id) > 512:
        raise HTTPException(400, "Unsupported credential identifier")
    db.execute(_insert(db, PasskeyGate).values(id=1, revision=0).on_conflict_do_nothing())
    db.execute(update(PasskeyGate).where(PasskeyGate.id == 1).values(revision=PasskeyGate.revision + 1))
    try:
        if db.scalar(select(func.count()).select_from(OwnerPasskey)) >= MAX_KEYS:
            raise HTTPException(409, "At most eight passkeys may be registered")
        if authority.startswith("setup:"):
            _authority(request, db, payload.enrollment_key)
            db.add(PasskeyEnrollment(digest=authority[6:]))
        if db.get(OwnerPasskey, credential_id) is not None:
            raise HTTPException(409, "Passkey already registered")
        db.add(OwnerPasskey(credential_id=credential_id,
            public_key=bytes_to_base64url(result.credential_public_key), sign_count=result.sign_count))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Enrollment was already completed") from None
    except HTTPException:
        db.rollback()
        raise
    response.delete_cookie(_cookie("register"), path="/api/passkeys")
    session = _session(response, credential_id) if authority.startswith("setup:") else {}
    return {"registered": True, **session}


@router.post("/login/options")
def login_options(request: Request, response: Response, db: Session = Depends(get_db)):
    _guard(request)
    _rate(db, request, "login")
    if db.scalar(select(OwnerPasskey.credential_id).limit(1)) is None:
        raise HTTPException(409, "Register a passkey with your one-time enrollment link first")
    rp_id, _ = _rp()
    options = generate_authentication_options(rp_id=rp_id,
        user_verification=UserVerificationRequirement.REQUIRED, timeout=TTL * 1000)
    cid = _new(db, response, "login", "", options.challenge)
    return {"ceremony_id": cid, "options": json.loads(options_to_json(options))}


@router.post("/login/verify")
def login_verify(payload: Ceremony, request: Request, response: Response,
                 db: Session = Depends(get_db)):
    _guard(request)
    challenge = _consume(db, request, payload.ceremony_id, "login", "")
    _cross_origin(payload.credential)
    credential_id = payload.credential.get("id")
    if not isinstance(credential_id, str) or len(credential_id) > 512:
        raise HTTPException(401, "Passkey authentication failed")
    row = db.get(OwnerPasskey, credential_id)
    if row is None:
        raise HTTPException(401, "Passkey authentication failed")
    handle = payload.credential.get("response", {}).get("userHandle")
    if handle is not None and handle != bytes_to_base64url(USER_ID):
        raise HTTPException(401, "Passkey authentication failed")
    rp_id, origin = _rp()
    old_count = row.sign_count
    try:
        result = verify_authentication_response(credential=payload.credential,
            expected_challenge=challenge, expected_origin=origin, expected_rp_id=rp_id,
            credential_public_key=base64url_to_bytes(row.public_key),
            credential_current_sign_count=old_count, require_user_verification=True)
    except Exception:
        raise HTTPException(401, "Passkey authentication failed") from None
    if bytes_to_base64url(result.credential_id) != row.credential_id:
        raise HTTPException(401, "Passkey authentication failed")
    changed = db.execute(update(OwnerPasskey).where(
        OwnerPasskey.credential_id == credential_id, OwnerPasskey.sign_count == old_count
    ).values(sign_count=result.new_sign_count, last_used_at=utcnow()))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Passkey changed during verification; sign in again")
    db.commit()
    response.delete_cookie(_cookie("login"), path="/api/passkeys")
    return _session(response, credential_id)


@router.get("/manage")
def manage(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    return {"passkeys": [{"id": row.credential_id,
        "created_at": row.created_at.isoformat() + "Z",
        "last_used_at": row.last_used_at.isoformat() + "Z" if row.last_used_at else None}
        for row in db.scalars(select(OwnerPasskey).order_by(OwnerPasskey.created_at))]}


@router.delete("/{credential_id}")
def revoke(credential_id: str, request: Request, _: dict = Depends(auth.require_owner_write),
           db: Session = Depends(get_db)):
    if request.headers.get("origin") != _rp()[1]:
        raise HTTPException(403, "Same-origin request required")
    db.execute(_insert(db, PasskeyGate).values(id=1, revision=0).on_conflict_do_nothing())
    db.execute(update(PasskeyGate).where(PasskeyGate.id == 1).values(revision=PasskeyGate.revision + 1))
    if db.scalar(select(func.count()).select_from(OwnerPasskey)) <= 1:
        db.rollback()
        raise HTTPException(409, "Register another passkey before removing the last one")
    row = db.get(OwnerPasskey, credential_id)
    if row is None:
        db.rollback()
        raise HTTPException(404, "Passkey not found")
    db.delete(row)
    db.execute(delete(OwnerSession))
    db.commit()
    return {"deleted": True, "sessions_revoked": True}
