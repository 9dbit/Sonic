"""Authenticated, evidence-backed knowledge graph. No demo nodes or AI inference."""
from __future__ import annotations

import hashlib
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth
from .brain import TOOLS
from .config import setting
from .db import Device, MemoryNote, MemorySource, MemoryLink, get_db, utcnow
from .memory import record, terms, SECRET_PATTERN

router = APIRouter()
NOTE_LIMIT = 500
TOPIC_LIMIT = 300


def graph_snapshot(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(MemoryNote)) or 0
    notes = db.scalars(select(MemoryNote).order_by(MemoryNote.id.desc()).limit(NOTE_LIMIT)).all()
    ids = {n.id for n in notes}
    sources = {s.memory_id: s for s in db.scalars(select(MemorySource).where(MemorySource.memory_id.in_(ids))).all()} if ids else {}
    nodes, edges = [], []

    def node(id, label, category, detail, **extra):
        nodes.append({'id': id, 'label': label, 'category': category, 'detail': detail, **extra})

    def edge(a, b, kind, label, evidence, **extra):
        edges.append({'id': f'{kind}:{a}:{b}', 'source': a, 'target': b, 'kind': kind, 'label': label, 'evidence': evidence, **extra})

    node('system:sonic', 'SONIC', 'system', 'Personal assistant. Graph reads persisted notes and the actual tool registry. Not an internal neural-network visualization.', source='application', state='configured')
    if notes:
        node('system:memory', 'Memory Vault', 'system', f'{total} persisted owner notes. Removing a note removes its graph node and saved relationships.', source='memory_notes', state='stored')
        edge('system:sonic', 'system:memory', 'structural', 'has memory store', 'memory_notes table')
    for note in notes:
        data = record(db, note, sources.get(note.id))
        node(data['node_id'], note.content[:64], 'memory', note.content, memory_id=note.id,
             source=data['source'], source_message_id=data['source_message_id'], created_at=data['created_at'], state='stored')
        edge('system:memory', data['node_id'], 'structural', 'contains saved note', f'memory_notes:{note.id}')

    # These are literal-word links. They do NOT assert semantic equivalence,
    # preferences, facts, or connected accounts. The UI marks them as derived.
    per_note = {note.id: terms(note.content, 6) for note in notes}
    counts = Counter(term for items in per_note.values() for term in items)
    selected = sorted(counts, key=lambda word: (-counts[word], word))[:TOPIC_LIMIT]
    for word in selected:
        tid = 'topic:' + hashlib.sha256(word.encode()).hexdigest()[:16]
        node(tid, word, 'topic', f'Literal term in {counts[word]} saved note(s). This is a derived lexical index, not an AI-inferred fact.', source='literal_term', state='derived')
        for nid, words in per_note.items():
            if word in words:
                edge(f'memory:{nid}', tid, 'lexical', 'contains term', f'memory_notes:{nid}', term=word)

    if ids:
        links = db.scalars(select(MemoryLink).where(MemoryLink.source_id.in_(ids), MemoryLink.target_id.in_(ids)).order_by(MemoryLink.id)).all()
        for link in links:
            edge(f'memory:{link.source_id}', f'memory:{link.target_id}', 'owner_link', link.label,
                 f'memory_links:{link.id}', link_id=link.id, confirmed=True, created_at=link.created_at.isoformat() + 'Z')
    for tool in TOOLS:
        tid = 'tool:' + tool['name']
        node(tid, tool['name'].replace('_', ' '), 'tool', tool['description'], source='tool_registry', state='available_with_policy')
        edge('system:sonic', tid, 'structural', 'declares tool', 'sonic.brain.TOOLS')
    device = db.get(Device, setting('SONIC_DEVICE_ID', 'TRADEVICEPC'))
    if device:
        age = max(0, int((utcnow() - device.last_seen).total_seconds()))
        did = 'device:' + device.id
        node(did, device.hostname or device.id, 'device', 'Registered read-only companion. Only system.status is allowed.',
             source='devices', state='online' if age < 120 else 'offline', last_seen_seconds_ago=age)
        edge('system:sonic', did, 'structural', 'registered companion', 'devices:' + device.id)
    degree = Counter()
    for item in edges:
        degree[item['source']] += 1
        degree[item['target']] += 1
    for item in nodes:
        item['degree'] = degree[item['id']]
    return {'schema': 'sonic.knowledge.v1', 'nodes': nodes, 'edges': edges,
            'counts': {'memories': total, 'displayed_memories': len(notes), 'nodes': len(nodes), 'edges': len(edges),
                       'categories': dict(Counter(item['category'] for item in nodes))},
            'truncated': total > len(notes) or len(counts) > TOPIC_LIMIT,
            'limits': {'notes': NOTE_LIMIT, 'topics': TOPIC_LIMIT},
            'provenance': 'Solid links: saved owner relations or application structure. Dashed links: literal terms derived from note text. No semantic links are inferred.',
            'generated_at': utcnow().isoformat() + 'Z'}


@router.get('/api/knowledge/graph')
def get_graph(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    return graph_snapshot(db)


class LinkForm(BaseModel):
    source_id: int = Field(gt=0)
    target_id: int = Field(gt=0)
    label: str = Field(default='related to', min_length=1, max_length=80)


@router.post('/api/knowledge/links')
def create_link(payload: LinkForm, _: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    label = payload.label.strip()
    if not label or SECRET_PATTERN.search(label):
        raise HTTPException(422, 'Invalid relation label')
    if payload.source_id == payload.target_id:
        raise HTTPException(422, 'Select two different memories')
    a, b = sorted([payload.source_id, payload.target_id])
    if not db.get(MemoryNote, a) or not db.get(MemoryNote, b):
        raise HTTPException(404, 'Both memories must exist')
    old = db.scalar(select(MemoryLink).where(MemoryLink.source_id == a, MemoryLink.target_id == b))
    if old:
        return {'id': old.id, 'created': False, 'label': old.label, 'confirmed': True}
    link = MemoryLink(source_id=a, target_id=b, label=label)
    db.add(link)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'This relation already exists') from None
    return {'id': link.id, 'created': True, 'label': link.label, 'confirmed': True}


@router.delete('/api/knowledge/links/{link_id}')
def remove_link(link_id: int, _: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    link = db.get(MemoryLink, link_id)
    if not link:
        raise HTTPException(404, 'Relation not found')
    db.delete(link)
    db.commit()
    return {'deleted': True}
