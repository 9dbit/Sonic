"""SONIC Artifact Studio v2.0: owner-only bounded artifact storage and revisions.

No code execution, filesystem writes, network fetches, shell invocations, or
deployment. HTML tools are previewed separately in an opaque-origin browser iframe.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth
from .db import ArtifactGate, ArtifactItem, ArtifactVersion, get_db, utcnow

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])
Kind = Literal["app", "code", "image", "audio", "video", "website"]
Source = Literal["manual", "import", "chat-draft"]
MAX_ITEMS = 100
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_VERSIONS = 12
MAX_TEXT_BYTES = 1024 * 1024
MAX_IMAGE_AUDIO_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 16 * 1024 * 1024

MEDIA = {
    "image": {"image/png", "image/jpeg", "image/webp"},
    "audio": {"audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/webm"},
    "video": {"video/mp4", "video/webm"},
}


class CreateArtifact(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Kind
    content: str = Field(min_length=1, max_length=23_000_000)
    mime: str = Field(default="", max_length=80)
    source: Source = "manual"


class ReviseArtifact(BaseModel):
    base_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=23_000_000)


def fail(status: int, message: str):
    raise HTTPException(status_code=status, detail=message)


def clean_name(value: str) -> str:
    name = value.strip()
    if not name or name != value or any(ord(c) < 32 for c in name):
        fail(422, "Nama artifact tidak valid")
    return name


def website_url(value: str) -> str:
    if len(value) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        fail(422, "URL website tidak valid")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        fail(422, "Hanya URL website HTTPS publik yang diizinkan")
    try:
        port = url.port
    except ValueError:
        fail(422, "Format port URL tidak valid")
    if port not in (None, 443):
        fail(422, "Port URL harus HTTPS standar")
    host = url.hostname.lower().rstrip(".")
    if host in ("localhost", "localhost.localdomain") or host.endswith((".local", ".internal", ".localhost")):
        fail(422, "Host lokal atau internal tidak diizinkan")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            fail(422, "Alamat IP privat atau khusus tidak diizinkan")
    except ValueError:
        if "." not in host or not re.fullmatch(r"[a-z0-9._-]+", host):
            fail(422, "Hostname publik tidak valid")
    return value


def check_signature(kind: str, mime: str, binary: bytes):
    signatures = {
        "image/png": binary.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": binary.startswith(b"\xff\xd8\xff"),
        "image/webp": binary.startswith(b"RIFF") and binary[8:12] == b"WEBP",
        "audio/mpeg": binary.startswith(b"ID3") or binary.startswith(b"\xff\xfb") or binary.startswith(b"\xff\xf3") or binary.startswith(b"\xff\xf2"),
        "audio/wav": binary.startswith(b"RIFF") and binary[8:12] == b"WAVE",
        "audio/ogg": binary.startswith(b"OggS"),
        "audio/mp4": binary[4:8] == b"ftyp",
        "audio/webm": binary.startswith(b"\x1a\x45\xdf\xa3"),
        "video/mp4": binary[4:8] == b"ftyp",
        "video/webm": binary.startswith(b"\x1a\x45\xdf\xa3"),
    }
    if not signatures.get(mime, False):
        fail(422, "File media tidak sesuai dengan format yang dinyatakan")


def validate_payload(kind: str, mime: str, content: str) -> tuple[str, int, str, str]:
    if kind in ("app", "code"):
        expected = "text/html" if kind == "app" else "text/plain"
        if mime not in ("", expected):
            fail(422, "MIME source tidak sesuai")
        data = content.encode("utf-8")
        if len(data) > MAX_TEXT_BYTES:
            fail(413, "Source maksimal 1 MiB")
        if kind == "app" and not content.strip():
            fail(422, "Source HTML kosong")
        return expected, len(data), hashlib.sha256(data).hexdigest(), content
    if kind == "website":
        if mime not in ("", "text/uri-list"):
            fail(422, "MIME website tidak sesuai")
        value = website_url(content)
        data = value.encode("utf-8")
        return "text/uri-list", len(data), hashlib.sha256(data).hexdigest(), value
    if kind not in MEDIA or mime not in MEDIA[kind]:
        fail(422, "Format artifact tidak diizinkan")
    prefix = "data:" + mime + ";base64,"
    if not content.startswith(prefix):
        fail(422, "Payload media harus memiliki MIME dan base64 yang benar")
    encoded = content[len(prefix):]
    limit = MAX_VIDEO_BYTES if kind == "video" else MAX_IMAGE_AUDIO_BYTES
    if len(encoded) > ((limit + 2) // 3) * 4 + 4:
        fail(413, "File melebihi batas penyimpanan artifact")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        fail(422, "Base64 media tidak valid")
    if not (16 <= len(data) <= limit):
        fail(413, "File di luar batas media")
    check_signature(kind, mime, data)
    return mime, len(data), hashlib.sha256(data).hexdigest(), content


def gate(db: Session):
    # Serialize quotas and versions on PostgreSQL and SQLite.
    if db.get(ArtifactGate, 1) is None:
        try:
            with db.begin_nested():
                db.add(ArtifactGate(id=1, revision=0))
                db.flush()
        except IntegrityError:
            pass
    db.execute(update(ArtifactGate).where(ArtifactGate.id == 1).values(
        revision=ArtifactGate.revision + 1))


def total_bytes(db: Session) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(ArtifactVersion.size), 0))) or 0)


def serialize(item: ArtifactItem, version: ArtifactVersion, *, content=False) -> dict:
    data = {
        "id": item.id, "name": item.name, "kind": item.kind, "mime": item.mime,
        "source": item.source, "version": item.version, "size": version.size,
        "sha256": version.digest, "created_at": item.created_at.isoformat() + "Z",
        "updated_at": item.updated_at.isoformat() + "Z", "preview": item.kind != "code",
    }
    if content:
        data["content"] = version.content
    return data


def required_item(db: Session, artifact_id: str) -> ArtifactItem:
    try:
        UUID(artifact_id)
    except (ValueError, AttributeError):
        fail(404, "Artifact tidak ditemukan")
    item = db.get(ArtifactItem, artifact_id)
    if item is None:
        fail(404, "Artifact tidak ditemukan")
    return item


@router.get("")
def list_artifacts(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    items = db.scalars(select(ArtifactItem).order_by(ArtifactItem.updated_at.desc()).limit(MAX_ITEMS)).all()
    entries = []
    for item in items:
        row = db.get(ArtifactVersion, (item.id, item.version))
        if row is not None:
            entries.append(serialize(item, row))
    return {"items": entries, "total": len(entries), "total_bytes": total_bytes(db),
            "quota_bytes": MAX_TOTAL_BYTES, "version_limit": MAX_VERSIONS}


@router.get("/{artifact_id}")
def get_artifact(artifact_id: str, version: int | None = Query(default=None, ge=1),
                 _: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    item = required_item(db, artifact_id)
    v = version or item.version
    record = db.get(ArtifactVersion, (item.id, v))
    if record is None:
        fail(404, "Versi artifact tidak ditemukan")
    versions = db.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id == item.id)
                          .order_by(ArtifactVersion.version.desc())).all()
    return {**serialize(item, record, content=True), "viewed_version": v,
            "versions": [{"version": row.version, "size": row.size, "sha256": row.digest,
                          "created_at": row.created_at.isoformat()+"Z"} for row in versions]}


@router.post("", status_code=201)
def create_artifact(payload: CreateArtifact, _: dict = Depends(auth.require_owner_write),
                    db: Session = Depends(get_db)):
    name = clean_name(payload.name)
    mime, size, digest, content = validate_payload(payload.kind, payload.mime, payload.content)
    gate(db)
    if (db.scalar(select(func.count()).select_from(ArtifactItem)) or 0) >= MAX_ITEMS:
        fail(409, "Batas jumlah artifact tercapai")
    if total_bytes(db) + size > MAX_TOTAL_BYTES:
        fail(409, "Batas penyimpanan artifact tercapai")
    ident = str(uuid4())
    item = ArtifactItem(id=ident, name=name, kind=payload.kind, mime=mime,
                        source=payload.source, version=1)
    version = ArtifactVersion(artifact_id=ident, version=1, content=content,
                              size=size, digest=digest)
    db.add_all([item, version])
    db.commit()
    return serialize(item, version)


@router.put("/{artifact_id}")
def revise_artifact(artifact_id: str, payload: ReviseArtifact,
                    _: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    gate(db)
    item = required_item(db, artifact_id)
    if payload.base_version != item.version:
        fail(409, "Artifact berubah di tab lain. Muat ulang sebelum menyimpan")
    if item.version >= MAX_VERSIONS:
        fail(409, "Batas versi artifact tercapai, ekspor dan buat artifact baru")
    mime, size, digest, content = validate_payload(item.kind, item.mime, payload.content)
    current = db.get(ArtifactVersion, (item.id, item.version))
    if current and current.digest == digest and (payload.name is None or payload.name == item.name):
        return serialize(item, current)
    if total_bytes(db) + size > MAX_TOTAL_BYTES:
        fail(409, "Batas penyimpanan artifact tercapai")
    item.version += 1
    item.updated_at = utcnow()
    if payload.name is not None:
        item.name = clean_name(payload.name)
    version = ArtifactVersion(artifact_id=item.id, version=item.version,
                              content=content, size=size, digest=digest)
    db.add(version)
    db.commit()
    return serialize(item, version)


@router.delete("/{artifact_id}")
def delete_artifact(artifact_id: str, _: dict = Depends(auth.require_owner_write),
                    db: Session = Depends(get_db)):
    gate(db)
    item = required_item(db, artifact_id)
    db.execute(delete(ArtifactVersion).where(ArtifactVersion.artifact_id == item.id))
    db.delete(item)
    db.commit()
    return {"deleted": True, "id": artifact_id}
