"""Optional disposable PostgreSQL integration, never the application DATABASE_URL."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from sonic.db import Base, ChatMessage, Device, DeviceJob, MemoryNote, MemorySource, MemoryLink, OwnerSession
from sonic.memory import save_note, delete_note
from sonic.knowledge import graph_snapshot


@pytest.mark.skipif(not os.environ.get('SONIC_TEST_POSTGRES_URL'), reason='Disposable PostgreSQL not configured')
def test_postgres_additive_schema_dedup_and_graph():
    url = os.environ['SONIC_TEST_POSTGRES_URL']
    if not url.startswith('postgresql+psycopg://') or 'localhost' not in url or '/sonic_test' not in url:
        pytest.fail('Only an explicit localhost sonic_test database is permitted')
    admin = create_engine(url)
    schema = 'sonic_qa_' + uuid4().hex
    with admin.begin() as connection:
        connection.execute(text('CREATE SCHEMA ' + schema))
    engine = admin.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(engine, tables=[MemoryNote.__table__, ChatMessage.__table__,
            Device.__table__, DeviceJob.__table__, OwnerSession.__table__])
        with Session(engine, expire_on_commit=False) as db:
            legacy = MemoryNote(content='Existing note must survive upgrade')
            db.add(legacy); db.commit(); legacy_id = legacy.id
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as db:
            assert db.get(MemoryNote, legacy_id).content == 'Existing note must survive upgrade'
            result = save_note(db, 'Existing note must survive upgrade')
            assert not result['created'] and result['memory_id'] == legacy_id
        def save_concurrently(_):
            with Session(engine, expire_on_commit=False) as db:
                return save_note(db, 'Saya suka bakso', source_kind='test_explicit')
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(save_concurrently, range(8)))
        assert len({item['memory_id'] for item in receipts}) == 1
        assert sum(item['created'] for item in receipts) == 1
        with Session(engine, expire_on_commit=False) as db:
            mid = receipts[0]['memory_id']
            db.add(MemoryLink(source_id=min(legacy_id, mid), target_id=max(legacy_id, mid), label='QA relationship'))
            db.commit()
            snapshot = graph_snapshot(db)
            assert snapshot['counts']['memories'] == 2
            assert any(edge['kind'] == 'owner_link' for edge in snapshot['edges'])
            delete_note(db, mid)
            assert db.get(MemoryNote, legacy_id)
            assert db.scalar(select(func.count()).select_from(MemorySource)) == 0
            assert db.scalar(select(func.count()).select_from(MemoryLink)) == 0
            assert graph_snapshot(db)['counts']['memories'] == 1
    finally:
        with admin.begin() as connection:
            connection.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        admin.dispose()
