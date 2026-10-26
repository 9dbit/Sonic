"""Workspace storage and owner boundaries, including stale edits and subtree trash."""
from uuid import uuid4

from sqlalchemy import select


def owner(client):
    r = client.post('/api/login', json={'token':'owner-test-token'})
    return {'X-Sonic-CSRF':r.json()['csrf']}


def create(client, headers, name, kind='folder', parent='root', **extra):
    return client.post('/api/workspace/items', headers=headers, json={
        'id':str(uuid4()),'name':name,'kind':kind,'parent_id':parent,**extra})


def test_owner_and_csrf_required(client):
    assert client.get('/api/workspace/items').status_code == 401
    headers = owner(client)
    assert create(client, {}, 'Private').status_code == 403
    folder = create(client, headers, 'Private').json()['item']
    assert client.patch('/api/workspace/items/'+folder['id'], json={
        'revision':1,'name':'Changed'}).status_code == 403
    assert client.delete('/api/workspace/items/'+folder['id']+'?revision=1').status_code == 403
    client.post('/api/logout', headers=headers)
    assert client.get('/api/workspace/items/'+folder['id']).status_code == 401


def test_hierarchy_notes_search_and_cloud_provenance(client):
    h = owner(client)
    folder = create(client,h,'Project').json()['item']
    note = create(client,h,'Rapat.md','text',folder['id'],content='Diskusi\n<script>alert(1)</script>').json()['item']
    assert note['storage'] == 'sonic_cloud'
    listing = client.get('/api/workspace/items', params={'parent_id':folder['id']}).json()
    assert listing['sync'] == 'none'
    assert [p['name'] for p in listing['breadcrumbs']] == ['SONIC Cloud','Project']
    assert listing['items'][0]['id'] == note['id']
    assert 'content' not in listing['items'][0]
    assert client.get('/api/workspace/items',params={'query':'RAPAT'}).json()['items'][0]['id'] == note['id']
    assert client.get('/api/workspace/items/'+note['id']).json()['content'].endswith('</script>')


def test_create_retry_exact_identity_and_name_conflict(client):
    h = owner(client)
    data = {'id':str(uuid4()),'name':'Catatan.md','kind':'text','content':'First'}
    a = client.post('/api/workspace/items',headers=h,json=data)
    b = client.post('/api/workspace/items',headers=h,json=data)
    assert a.json()['created'] and not b.json()['created']
    assert a.json()['item']['id'] == b.json()['item']['id']
    assert create(client,h,'CATATAN.md','text').status_code == 409
    assert client.post('/api/workspace/items',headers=h,json={**data,'content':'Other'}).status_code == 409


def test_stale_edit_rename_move_and_restore_preserve_text(client):
    h = owner(client)
    dest = create(client,h,'Destination').json()['item']
    note = create(client,h,'Note.txt','text',content='Original').json()['item']
    url = '/api/workspace/items/'+note['id']
    assert client.patch(url,headers=h,json={'revision':1,'content':'Saved elsewhere'}).status_code == 200
    assert client.patch(url,headers=h,json={'revision':1,'content':'Stale overwrite'}).status_code == 409
    moved = client.patch(url,headers=h,json={'revision':2,'name':'Moved.md','parent_id':dest['id']}).json()
    assert moved['content'] == 'Saved elsewhere' and moved['revision'] == 3
    assert client.delete(url+'?revision=2',headers=h).status_code == 409
    assert client.delete(url+'?revision=3',headers=h).json()['trashed']
    assert client.get(url).status_code == 409
    restored = client.post(url+'/restore',headers=h,json={'revision':4})
    assert restored.status_code == 200 and not restored.json()['trashed']
    assert client.get(url).json()['content'] == 'Saved elsewhere'


def test_trash_subtree_cannot_be_read_edited_or_created_inside(client):
    h = owner(client)
    parent = create(client,h,'Parent').json()['item']
    child = create(client,h,'Child',parent=parent['id']).json()['item']
    note = create(client,h,'Private.md','text',child['id'],content='preserve').json()['item']
    assert client.delete('/api/workspace/items/'+parent['id']+'?revision=1',headers=h).status_code == 200
    assert not client.get('/api/workspace/items',params={'query':'Private'}).json()['items']
    assert client.get('/api/workspace/items/'+note['id']).status_code == 409
    assert client.patch('/api/workspace/items/'+note['id'],headers=h,json={'revision':1,'content':'lost'}).status_code == 409
    assert create(client,h,'New',parent=child['id']).status_code == 409
    assert client.post('/api/workspace/items/'+parent['id']+'/restore',headers=h,json={'revision':2}).status_code == 200
    assert client.get('/api/workspace/items/'+note['id']).json()['content'] == 'preserve'


def test_restore_collision_and_cycle_rejected(client):
    h = owner(client)
    parent = create(client,h,'Parent').json()['item']
    child = create(client,h,'Child',parent=parent['id']).json()['item']
    assert client.patch('/api/workspace/items/'+parent['id'],headers=h,json={'revision':1,'parent_id':child['id']}).status_code == 422
    assert client.delete('/api/workspace/items/'+parent['id']+'?revision=1',headers=h).status_code == 200
    create(client,h,'Parent')
    assert client.post('/api/workspace/items/'+parent['id']+'/restore',headers=h,json={'revision':2}).status_code == 409
    assert client.get('/api/workspace/items',params={'trash':True}).json()['items'][0]['trashed']


def test_bad_names_extensions_and_oversize_rejected(client):
    h = owner(client)
    for name in ('../outside','C:\\secrets','COM1.txt','Folder.',' trailing','a/b','a\x00b'):
        assert create(client,h,name).status_code == 422, name
    assert create(client,h,'run.exe','text').status_code == 422
    assert create(client,h,'Folder',content='unexpected').status_code == 422
    assert create(client,h,'Big.md','text',content='x'*100001).status_code == 422
    assert create(client,h,'Absent',parent=str(uuid4())).status_code == 404


def test_quota_includes_trash_and_utf8_bytes(client,monkeypatch):
    import sonic.workspace as ws
    monkeypatch.setattr(ws,'MAX_ITEMS',2)
    monkeypatch.setattr(ws,'MAX_BYTES',12)
    h = owner(client)
    note = create(client,h,'Note.md','text',content='😀😀').json()['item']
    assert client.delete('/api/workspace/items/'+note['id']+'?revision=1',headers=h).status_code == 200
    assert create(client,h,'Other.md','text',content='😀😀').status_code == 409
    assert create(client,h,'Other.md','text',content='😀').status_code == 200
    assert create(client,h,'Folder').status_code == 409


def test_workspace_survives_new_owner_session_and_database_reopen(client):
    from sonic.db import WorkspaceItem, session_factory
    h = owner(client)
    note = create(client,h,'Durable.md','text',content='Saved').json()['item']
    client.post('/api/logout',headers=h)
    owner(client)
    with session_factory()() as db:
        assert db.scalar(select(WorkspaceItem).where(WorkspaceItem.id==note['id'])).content == 'Saved'
    assert client.get('/api/workspace/items/'+note['id']).json()['content'] == 'Saved'


def test_depth_limit_includes_moved_subtree(client):
    h = owner(client)
    parent = 'root'
    levels = []
    for i in range(8):
        folder = create(client,h,f'Level {i}',parent=parent)
        assert folder.status_code == 200
        parent = folder.json()['item']['id']
        levels.append(parent)
    assert create(client,h,'Ninth',parent=parent).status_code == 422
    assert create(client,h,'Deep.md','text',parent,content='Allowed at level eight').status_code == 200
    top = create(client,h,'Move').json()['item']
    create(client,h,'Child',parent=top['id'])
    assert client.patch('/api/workspace/items/'+top['id'],headers=h,json={
        'revision':1,'parent_id':levels[6]}).status_code == 422


def test_postgres_workspace_writers_serialize():
    import os
    from concurrent.futures import ThreadPoolExecutor
    import pytest
    from fastapi import HTTPException
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from sonic.db import Base
    from sonic.workspace import create as create_item, edit, CreateItem, EditItem
    url = os.environ.get('SONIC_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Disposable PostgreSQL not configured')
    if not url.startswith('postgresql+psycopg://') or 'localhost' not in url or '/sonic_test' not in url:
        pytest.fail('Only an explicit localhost sonic_test database is permitted')
    admin = create_engine(url)
    schema = 'sonic_workspace_qa_'+uuid4().hex
    with admin.begin() as conn:
        conn.execute(text('CREATE SCHEMA '+schema))
    engine = admin.execution_options(schema_translate_map={None:schema})
    try:
        Base.metadata.create_all(engine)
        def same_name(i):
            with Session(engine,expire_on_commit=False) as db:
                try:
                    return create_item(CreateItem(id=str(uuid4()),name='Concurrent.md',kind='text'),{},db)['item']['id']
                except HTTPException as exc:
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(same_name,range(2)))
        assert results.count(409) == 1
        item_id = next(x for x in results if isinstance(x,str))
        def concurrent_edit(i):
            with Session(engine,expire_on_commit=False) as db:
                try:
                    return edit(item_id,EditItem(revision=1,content=str(i)),{},db)['revision']
                except HTTPException as exc:
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(concurrent_edit,range(2))) == [2,409]
    finally:
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()
