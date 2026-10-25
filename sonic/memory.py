"""Explicit owner intent, durable memory receipts and provenance.

Only anchored imperatives authorize writes. Quoted examples, questions and
negations do not. This parser is deliberately conservative, not an NLP claim.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .db import MemoryNote, MemorySource, MemoryLink

SECRET_PATTERN = re.compile(
    r"(sk-[a-zA-Z0-9_-]{12,}|password|kata\s*sandi|api.?key|secret|private.?key|"
    r"bearer\s+\S+|token\s*[:=]|-----BEGIN .*PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{16,})", re.I
)
NEGATION = re.compile(r"\b(?:jangan(?:lah)?|tidak\s+usah|tak\s+perlu|ga\s+usah|do\s+not|don['\u2019]?t|never)\s+(?:simpan|ingat|catat|save|store|remember|memorize)\b", re.I)
LEADING = re.compile(r"^(?:(?:hey|hai|halo)\s+)?(?:sonic[\s,:.!-]+)?(?:(?:tolong|mohon|please)\s+)?", re.I)
VERB = re.compile(r"^(ingat(?:lah)?|catat(?:lah)?|simpan(?:kan)?|remember|memorize|save|store)\b\s*", re.I)
DESTINATION = re.compile(
    r"^(?:(?:ini|this|it)\s+)?(?:(?:ke|di|dalam)\s+(?:memori(?:ku|mu|nya)?|memory)(?:\s+saya)?|"
    r"(?:in|to|into)\s+(?:(?:my|your|the)\s+)?(?:long[- ]term\s+)?memory|as\s+(?:a\s+)?memory)\b\s*", re.I
)
QUESTION = re.compile(r"^(?:apa(?:kah)?|siapa|kapan|bagaimana|kenapa|mengapa|what|who|when|how|whether|if)\b", re.I)
STOP_WORDS = set("saya aku anda kamu dia kita kami mereka ini itu bahwa yang dan atau di ke dari pada dalam dengan untuk adalah sudah belum pernah akan bisa tolong sonic ingat catat simpan memori memoriku memory remember save store please the a an and or to of in on is are i my me you your that this what who when how apa apakah siapa kapan bagaimana ada mana saja lagi suka prefer like likes saya bahwasanya".split())


@dataclass(frozen=True)
class MemoryIntent:
    fact: str
    language: str


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def parse_memory_intent(message: str) -> MemoryIntent | None:
    if not isinstance(message, str):
        return None
    text = normalize(message)
    if not text or text[0] in '\"\'`>' or '```' in text or NEGATION.search(text):
        return None
    text = LEADING.sub('', text, count=1)
    # Also accept "Tolong SONIC, ..." without unanchored substring matching.
    text = re.sub(r'^sonic[\s,:.!-]+', '', text, flags=re.I)
    match = VERB.match(text)
    if not match:
        return None
    verb, rest = match.group(1).lower(), text[match.end():].strip()
    dest = DESTINATION.match(rest)
    if dest:
        rest = rest[dest.end():]
    elif verb.startswith('simpan') or verb in {'save', 'store'}:
        if not re.match(r'^(?:fakta|informasi|catatan|ini|this|fact|note)\b', rest, re.I):
            return None
        rest = re.sub(r'^(?:fakta|informasi|catatan|ini|this|fact|note)\s*', '', rest, flags=re.I)
    rest = re.sub(r'^(?:ini|this)\s*:', '', rest, flags=re.I).strip(' :,-')
    rest = re.sub(r'^(?:bahwa|that)\s+', '', rest, flags=re.I).strip()
    if rest.endswith('?') or QUESTION.match(rest) or rest.lower() in {'ini', 'itu', 'this', 'that', ''}:
        return None
    if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in '\"\'':
        rest = rest[1:-1].strip()
    return MemoryIntent(rest, 'en' if verb in {'remember', 'memorize', 'save', 'store'} else 'id')


def validate_memory(text: str) -> str:
    if not isinstance(text, str):
        raise HTTPException(422, 'Memory must be text')
    content = normalize(text)
    if not 3 <= len(content) <= 500:
        raise HTTPException(422, 'Memory must contain 3-500 characters')
    if SECRET_PATTERN.search(content):
        raise HTTPException(422, 'Credentials must not be stored in memory')
    return content


def record(db: Session, note: MemoryNote, source: MemorySource | None = None) -> dict:
    if source is None:
        source = db.get(MemorySource, note.id)
    return {
        'id': note.id, 'text': note.content, 'created_at': note.created_at.isoformat() + 'Z',
        'source': source.source_kind if source else 'legacy_memory',
        'source_message_id': source.source_message_id if source else None,
        'node_id': f'memory:{note.id}'
    }


def _receipt(db: Session, note: MemoryNote, created: bool) -> dict:
    return {'saved': True, 'created': created, 'memory_id': note.id, **record(db, note)}


def save_note(db: Session, text: str, *, source_kind: str = 'owner_form', source_message_id: int | None = None) -> dict:
    """Commit before returning a receipt; a digest prevents concurrent duplicates.

    Existing memory_notes rows remain intact. Metadata uses an additive table.
    """
    content = validate_memory(text)
    digest = hashlib.sha256(content.casefold().encode('utf-8')).hexdigest()
    try:
        meta = db.scalar(select(MemorySource).where(MemorySource.content_sha256 == digest))
        if meta:
            old = db.get(MemoryNote, meta.memory_id)
            if old:
                return _receipt(db, old, False)
        # Respect legacy notes created before provenance was introduced.
        old = db.scalar(select(MemoryNote).where(func.lower(func.trim(MemoryNote.content)) == content.lower()).order_by(MemoryNote.id).limit(1))
        if old:
            return _receipt(db, old, False)
        note = MemoryNote(content=content)
        db.add(note)
        db.flush()
        db.add(MemorySource(memory_id=note.id, content_sha256=digest, source_kind=source_kind,
                            source_message_id=source_message_id))
        db.commit()
        return _receipt(db, note, True)
    except IntegrityError:
        db.rollback()
        meta = db.scalar(select(MemorySource).where(MemorySource.content_sha256 == digest))
        note = db.get(MemoryNote, meta.memory_id) if meta else None
        if note:
            return _receipt(db, note, False)
        raise HTTPException(503, 'Memory could not be saved; please retry') from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, 'Memory storage unavailable; no save confirmed') from None


def delete_note(db: Session, memory_id: int) -> None:
    note = db.get(MemoryNote, memory_id)
    if note is None:
        raise HTTPException(404, 'Memory not found')
    try:
        db.execute(delete(MemoryLink).where(or_(MemoryLink.source_id == memory_id, MemoryLink.target_id == memory_id)))
        db.execute(delete(MemorySource).where(MemorySource.memory_id == memory_id))
        db.delete(note)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, 'Memory could not be deleted') from None


def terms(text: str, maximum: int = 8) -> list[str]:
    seen = []
    for word in re.findall(r'[^\W_][\w-]{2,39}', normalize(text).casefold(), flags=re.UNICODE):
        if word not in STOP_WORDS and not word.isdigit() and word not in seen:
            seen.append(word)
        if len(seen) >= maximum:
            break
    return seen


def search_notes(db: Session, query: str, limit: int = 8) -> list[dict]:
    tokens = terms(query, 8)
    statement = select(MemoryNote)
    if tokens:
        escaped = [t.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') for t in tokens]
        statement = statement.where(or_(*(MemoryNote.content.ilike('%' + t + '%', escape='\\') for t in escaped)))
    rows = db.scalars(statement.order_by(MemoryNote.id.desc()).limit(min(limit, 20))).all()
    return [record(db, note) for note in rows]
