"""Durable, owner-only cloud folders and text notes. Never implies PC/Drive sync."""
import hashlib
import json
import re
import unicodedata
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth
from .db import WorkspaceGate, WorkspaceItem, get_db, utcnow

router = APIRouter(prefix='/api/workspace', tags=['workspace'])
MAX_ITEMS = 1000
MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 100000


class CreateItem(BaseModel):
    id: str = Field(min_length=36, max_length=36)
    parent_id: str = Field(default='root', max_length=36)
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern=r'^(folder|text)$')
    content: str = Field(default='', max_length=MAX_TEXT)


class EditItem(BaseModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: str | None = Field(default=None, max_length=36)
    content: str | None = Field(default=None, max_length=MAX_TEXT)


class RestoreItem(BaseModel):
    revision: int = Field(ge=1)


def fail(code, text):
    raise HTTPException(code, text)


def safe_name(raw, kind):
    name = unicodedata.normalize('NFC', raw)
    try:
        name.encode('utf-8')
    except UnicodeEncodeError:
        fail(422, 'Nama harus berupa teks Unicode yang valid.')
    if (name != name.strip() or name in ('.', '..') or name.endswith('.') or
            any(ord(c) < 32 or c in '/\\:<>"|?*' for c in name) or
            re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', name, re.I)):
        fail(422, 'Nama tidak valid. Gunakan satu nama tanpa pemisah folder.')
    if kind == 'text' and not name.lower().endswith(('.txt', '.md')):
        fail(422, 'Catatan mendukung file .txt atau .md.')
    return name


def text_bytes(text):
    try:
        return len(text.encode('utf-8'))
    except UnicodeEncodeError:
        fail(422, 'Isi catatan harus berupa teks Unicode yang valid.')


def slot(parent, name):
    return hashlib.sha256((parent + '/' + name.casefold()).encode()).hexdigest()


def lock(db):
    # UPDATE serializes hierarchy/quotas on both PostgreSQL and SQLite. All
    # writes hold this transaction until commit, including ancestor checks.
    if not db.get(WorkspaceGate, 1):
        try:
            with db.begin_nested():
                db.add(WorkspaceGate(id=1, revision=0))
                db.flush()
        except IntegrityError:
            pass
    db.execute(update(WorkspaceGate).where(WorkspaceGate.id == 1).values(
        revision=WorkspaceGate.revision + 1))


def get_item(db, item_id):
    item = db.get(WorkspaceItem, item_id)
    if not item:
        fail(404, 'File atau folder tidak ditemukan.')
    return item


def ancestors(db, parent_id, reject_id=None):
    trail, seen = [], set()
    while parent_id != 'root':
        if parent_id == reject_id or parent_id in seen:
            fail(422, 'Folder tidak dapat dipindah ke dirinya atau turunannya.')
        seen.add(parent_id)
        if len(seen) > 8:
            fail(422, 'Maksimal delapan tingkat folder.')
        item = get_item(db, parent_id)
        if item.kind != 'folder' or item.trashed_at:
            fail(409, 'Folder tujuan tidak tersedia. Pulihkan dari Trash terlebih dahulu.')
        trail.append(item)
        parent_id = item.parent_id
    return trail


def accessible(db, item):
    if item.trashed_at:
        fail(409, 'Item berada di Trash. Pulihkan sebelum mengedit.')
    ancestors(db, item.parent_id)


def check_revision(item, revision):
    if item.revision != revision:
        fail(409, 'Versi berubah di tab lain. Muat ulang file sebelum menyimpan.')


def quota(db, extra=0, old=''):
    items = db.scalars(select(WorkspaceItem)).all()
    if len(items) + extra > MAX_ITEMS:
        fail(409, 'Batas workspace 1.000 item termasuk Trash tercapai.')
    total = sum(len(i.content.encode()) for i in items) - len(old.encode())
    return total


def serialize(item, content=False):
    data = dict(id=item.id, parent_id=item.parent_id, name=item.name, kind=item.kind,
                revision=item.revision, bytes=len(item.content.encode()),
                trashed=bool(item.trashed_at), updated_at=item.updated_at.isoformat()+'Z',
                storage='sonic_cloud')
    if content:
        data['content'] = item.content
    return data


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, 'Nama sudah digunakan dalam folder tujuan.')


@router.get('/items')
def listing(parent_id: str = Query(default='root', max_length=36),
            query: str = Query(default='', max_length=100), trash: bool = False,
            _: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    trail = ancestors(db, parent_id)
    all_items = db.scalars(select(WorkspaceItem).order_by(WorkspaceItem.name)).all()
    lookup = {i.id: i for i in all_items}

    def visible(i):
        seen = set()
        while i:
            if i.trashed_at or i.id in seen:
                return False
            seen.add(i.id)
            i = lookup.get(i.parent_id)
        return True

    rows = [i for i in all_items if (bool(i.trashed_at) if trash else visible(i))]
    if query.strip():
        rows = [i for i in rows if query.casefold().strip() in i.name.casefold()]
    elif not trash:
        rows = [i for i in rows if i.parent_id == parent_id]
    rows.sort(key=lambda i: (i.kind != 'folder', i.name.casefold()))
    return dict(items=[serialize(i) for i in rows],
                folders=[serialize(i) for i in all_items if i.kind == 'folder' and visible(i)],
                breadcrumbs=[{'id':'root','name':'SONIC Cloud'}]+[
                    {'id':i.id,'name':i.name} for i in reversed(trail)],
                storage='sonic_cloud', sync='none',
                notice='Tersimpan di SONIC Cloud. Belum disinkronkan ke PC atau Google Drive.',
                limits={'items':MAX_ITEMS,'text_characters':MAX_TEXT,'total_bytes':MAX_BYTES})


@router.get('/items/{item_id}')
def read(item_id: str, _: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    item = get_item(db, item_id)
    accessible(db, item)
    return serialize(item, True)


@router.post('/items')
def create(payload: CreateItem, _: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    try:
        if str(UUID(payload.id)) != payload.id:
            raise ValueError()
    except ValueError:
        fail(422, 'Identitas file tidak valid.')
    name = safe_name(payload.name, payload.kind)
    if payload.kind == 'folder' and payload.content:
        fail(422, 'Folder tidak berisi teks catatan.')
    identity = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()
    lock(db)
    previous = db.get(WorkspaceItem, payload.id)
    if previous:
        if previous.create_hash != identity:
            fail(409, 'Identitas permintaan sudah dipakai untuk item lain.')
        return dict(item=serialize(previous, True), created=False)
    trail = ancestors(db, payload.parent_id)
    if payload.kind == 'folder' and len(trail) >= 8:
        fail(422, 'Maksimal delapan tingkat folder.')
    if quota(db, extra=1) + text_bytes(payload.content) > MAX_BYTES:
        fail(409, 'Batas penyimpanan teks workspace 10 MB tercapai.')
    item = WorkspaceItem(id=payload.id, parent_id=payload.parent_id, name=name,
                         kind=payload.kind, content=payload.content, create_hash=identity,
                         slot=slot(payload.parent_id, name))
    db.add(item)
    commit(db)
    return dict(item=serialize(item, True), created=True)


@router.patch('/items/{item_id}')
def edit(item_id: str, payload: EditItem, _: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    lock(db)
    item = get_item(db, item_id)
    accessible(db, item)
    check_revision(item, payload.revision)
    name = safe_name(payload.name, item.kind) if payload.name is not None else item.name
    parent = payload.parent_id if payload.parent_id is not None else item.parent_id
    ancestors(db, parent, item.id)
    if parent != item.parent_id and item.kind == 'folder':
        # Include the entire subtree depth, not merely the moved root.
        all_items = db.scalars(select(WorkspaceItem)).all()
        children = {}
        for child in all_items:
            children.setdefault(child.parent_id, []).append(child.id)
        def depth(key):
            folder_ids = {i.id for i in all_items if i.kind == 'folder'}
            return 1 + max((depth(c) for c in children.get(key, []) if c in folder_ids), default=0)
        if len(ancestors(db, parent)) + depth(item.id) > 8:
            fail(422, 'Pemindahan melebihi delapan tingkat folder.')
    if payload.content is not None:
        if item.kind != 'text':
            fail(422, 'Folder tidak dapat diedit sebagai catatan.')
        if quota(db, old=item.content) + text_bytes(payload.content) > MAX_BYTES:
            fail(409, 'Batas penyimpanan teks workspace 10 MB tercapai.')
        item.content = payload.content
    item.name, item.parent_id, item.slot = name, parent, slot(parent, name)
    item.revision += 1
    item.updated_at = utcnow()
    commit(db)
    return serialize(item, True)


@router.delete('/items/{item_id}')
def trash(item_id: str, revision: int = Query(ge=1), _: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    lock(db)
    item = get_item(db, item_id)
    accessible(db, item)
    check_revision(item, revision)
    item.trashed_at = item.updated_at = utcnow()
    item.slot = None
    item.revision += 1
    commit(db)
    return serialize(item)


@router.post('/items/{item_id}/restore')
def restore(item_id: str, payload: RestoreItem, _: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    lock(db)
    item = get_item(db, item_id)
    check_revision(item, payload.revision)
    if not item.trashed_at:
        fail(409, 'Item sudah berada di workspace.')
    ancestors(db, item.parent_id)
    item.trashed_at = None
    item.slot = slot(item.parent_id, item.name)
    item.revision += 1
    item.updated_at = utcnow()
    commit(db)
    return serialize(item)
