"""SONIC personal-guest pairing: least-privilege iPhone access to uptime ONLY.

A registered Windows Companion can issue a one-time, 15-minute HTTPS pairing link.
A browser that redeems it receives an HttpOnly, Secure, 90-day capability cookie.
This never creates an OwnerSession or authorizes files, memory, PC commands,
workspace, missions, device telemetry or owner chat tools.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, String, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from . import auth
from .config import public_url
from .db import Base, get_db, utcnow
from .preview import preview_active, paid_preview_enabled, guest, _verified_guest_cookie, _mac
from .uptime import report as uptime_report

router = APIRouter(prefix="/api/preview/trusted", tags=["trusted-preview"])
COOKIE = "sonic_personal_preview"
PAIR_SECONDS = 15 * 60
TRUST_SECONDS = 90 * 86400


class TrustedPair(Base):
    __tablename__ = "trusted_iphone_pairings_v151"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TrustedGuest(Base):
    __tablename__ = "trusted_iphone_sessions_v151"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Claim(Strict):
    token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def paired(request: Request, db: Session) -> bool:
    """A verified, revocable personal-cookie capability, never an owner session."""
    if not preview_active():
        return False
    token = request.cookies.get(COOKIE, "")
    if not isinstance(token, str) or not 40 <= len(token) <= 100:
        return False
    try:
        hashed = digest(token)
    except (UnicodeEncodeError, ValueError):
        return False
    row = db.get(TrustedGuest, hashed)
    return row is not None and row.expires_at > utcnow()


def read_capability(request: Request, db: Session = Depends(get_db)) -> dict:
    """Same-origin signed guest + CSRF + personal capability, read only."""
    if not preview_active() or not paid_preview_enabled():
        raise HTTPException(404, "Personal preview disabled")
    from .preview import COOKIE as GUEST_COOKIE
    raw = _verified_guest_cookie(request.cookies.get(GUEST_COOKIE, ""))
    if raw is None:
        raise HTTPException(403, "Refresh to initialize preview session")
    expected = public_url().rstrip("/") or str(request.base_url).rstrip("/")
    origin = request.headers.get("origin", "")
    if origin and origin != expected:
        raise HTTPException(403, "Cross-origin request denied")
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        raise HTTPException(403, "Cross-site request denied")
    csrf = request.headers.get("x-sonic-preview-csrf", "")
    if not csrf or not hmac.compare_digest(csrf, _mac("csrf:" + raw)):
        raise HTTPException(403, "Signed preview CSRF required")
    if not paired(request, db):
        raise HTTPException(403, "This iPhone has not been paired with SONIC")
    return {"scope": "uptime.read"}


@router.post("/issue")
def issue_pair(request: Request, db: Session = Depends(get_db)):
    """Only the registered Companion can authorize pairing new browsers."""
    auth.require_device(request)
    if not preview_active() or not paid_preview_enabled():
        raise HTTPException(409, "Personal preview pairing is disabled")
    now = utcnow()
    db.execute(delete(TrustedPair).where(TrustedPair.expires_at <= now))
    db.execute(delete(TrustedPair).where(TrustedPair.redeemed_at.is_(None)))
    # Issuing a new link automatically invalidates all previous unused links.
    token = secrets.token_urlsafe(32)
    db.add(TrustedPair(id=digest(token), expires_at=now+timedelta(seconds=PAIR_SECONDS)))
    db.commit()
    return {"pair_url": public_url().rstrip("/")+"/#sonic-pair="+token,
            "expires_in_seconds": PAIR_SECONDS, "one_time": True,
            "scope": ["uptime.read", "uptime.voice"]}


@router.post("/claim")
def claim_pair(data: Claim, request: Request, response: Response,
               _: dict = Depends(guest), db: Session = Depends(get_db)):
    if not preview_active():
        raise HTTPException(404, "Preview disabled")
    row = db.scalar(select(TrustedPair).where(
        TrustedPair.id == digest(data.token)).with_for_update())
    if row is None or row.redeemed_at is not None or row.expires_at <= utcnow():
        raise HTTPException(410, "Pairing link expired or already used")
    token = secrets.token_urlsafe(32)
    now = utcnow()
    row.redeemed_at = now
    # Only the most recently paired iPhone remains trusted.
    db.execute(delete(TrustedGuest))
    db.add(TrustedGuest(id=digest(token),
                        expires_at=now+timedelta(seconds=TRUST_SECONDS)))
    db.commit()
    response.set_cookie(COOKIE, token, max_age=TRUST_SECONDS, httponly=True,
                        secure=public_url().startswith("https://"),
                        samesite="strict", path="/")
    return {"paired": True, "capabilities": ["uptime.read", "uptime.voice"],
            "expires_in_days": 90, "owner_access": False}


@router.get("/uptime")
def personal_uptime(_: dict = Depends(read_capability),
                    db: Session = Depends(get_db)):
    return uptime_report(db, 24)


@router.post("/unpair")
def unpair(request: Request, response: Response,
           _: dict = Depends(guest), db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    if token and 40 <= len(token) <= 100:
        try:
            row = db.get(TrustedGuest, digest(token))
        except UnicodeEncodeError:
            row = None
        if row is not None:
            db.delete(row)
            db.commit()
    response.delete_cookie(COOKIE, path="/", samesite="strict",
                           secure=public_url().startswith("https://"))
    return {"paired": False}


@router.post("/revoke-all")
def revoke_all(request: Request, db: Session = Depends(get_db)):
    """Emergency revoke from authorized registered TRADEVICEPC only."""
    auth.require_device(request)
    db.execute(delete(TrustedGuest))
    db.execute(delete(TrustedPair))
    db.commit()
    return {"all_personal_sessions_revoked": True}
