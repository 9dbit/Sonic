import copy
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sonic.memory import parse_memory_intent, save_note, search_notes
from sonic.db import MemoryNote, MemorySource, MemoryLink, session_factory


def login(client):
    r = client.post('/api/login', json={'token': 'owner-test-token'})
    assert r.status_code == 200, r.text
    return {'X-Sonic-CSRF': r.json()['csrf']}


@pytest.mark.parametrize('message', [
    'SONIC, simpan ke memoriku bahwa saya suka bakso',
    'SONIC, simpan ke memori bahwa saya suka bakso',
    'simpan ke memori saya bahwa saya suka bakso',
    'Tolong SONIC, ingat bahwa saya suka bakso',
    'Sonic, tolong catat bahwa saya suka bakso',
    'Ingat saya suka bakso', 'Catat ini: saya suka bakso',
    'Simpan ini: saya suka bakso', 'Please remember that I like bakso',
    'save to my memory that I like bakso', 'Store this in my memory: I like bakso',
    'Ingat bahwa saya tidak suka kopi',
])
def test_explicit_positive_intents(message):
    assert parse_memory_intent(message) is not None


@pytest.mark.parametrize('message', [
    'Jangan ingat bahwa saya suka bakso', 'SONIC, jangan simpan ke memoriku bahwa saya suka bakso',
    "Don't remember that I like bakso", 'Do not save this in my memory: coffee',
    'Apa kamu ingat saya suka bakso?', 'Bagaimana cara simpan ke memori?',
    'Contoh perintah: ingat saya suka bakso', 'Kalau saya bilang ingat saya suka bakso, apa yang terjadi?',
    '"SONIC, simpan ke memoriku bahwa saya suka bakso"',
    '`remember I like bakso`', 'Tolong jelaskan arti remember that I like bakso',
    'Ingat apa yang saya suka?', 'Remember what I said?', 'Simpan dokumen itu',
    'Ingat saya suka bakso, tapi jangan simpan ke memori', 'Ingat ini',
])
def test_questions_negations_examples_do_not_authorize(message):
    assert parse_memory_intent(message) is None


def test_exact_reported_bug_has_durable_receipt_without_provider(client):
    headers = login(client)
    message = 'SONIC, simpan ke memoriku bahwa saya suka bakso'
    r = client.post('/api/chat', json={'message': message}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()['reply'].startswith('Tersimpan')
    e = r.json()['memory_events'][0]
    assert e['saved'] is True and e['created'] is True
    assert e['text'] == 'saya suka bakso'
    assert e['source'] == 'chat_explicit' and e['source_message_id']
    notes = client.get('/api/memories').json()['memories']
    assert notes[0]['id'] == e['memory_id']
    again = client.post('/api/chat', json={'message': message}, headers=headers)
    assert again.status_code == 200
    assert again.json()['memory_events'][0]['created'] is False
    assert client.get('/api/memories').json()['total'] == 1


def test_memory_and_graph_survive_restart_and_relogin(client):
    h = login(client)
    r = client.post('/api/chat', json={'message': 'Ingat saya suka bakso'}, headers=h)
    mid = r.json()['memory_events'][0]['memory_id']
    assert client.post('/api/logout', headers=h).status_code == 200
    import sonic.db as storage
    storage._engine.dispose(); storage._engine = None; storage._Session = None
    login(client)
    assert client.get('/api/memories').json()['memories'][0]['id'] == mid
    assert any(n['id'] == f'memory:{mid}' for n in client.get('/api/knowledge/graph').json()['nodes'])


def test_graph_auth_and_counts_no_fake_memories(client):
    assert client.get('/api/knowledge/graph').status_code == 401
    login(client)
    data = client.get('/api/knowledge/graph').json()
    assert data['counts']['memories'] == 0
    assert not any(n['category'] in {'memory', 'topic', 'device'} for n in data['nodes'])
    assert data['counts']['nodes'] == len(data['nodes'])
    assert data['counts']['edges'] == len(data['edges'])


def test_graph_provenance_derived_terms_and_confirmed_links(client):
    h = login(client)
    a = client.post('/api/memories', json={'text': 'Saya suka bakso Bandung'}, headers=h).json()['id']
    b = client.post('/api/memories', json={'text': 'Kantor saya di Bandung'}, headers=h).json()['id']
    payload = {'source_id': a, 'target_id': b, 'label': 'konteks kota'}
    assert client.post('/api/knowledge/links', json=payload).status_code == 403
    r = client.post('/api/knowledge/links', json=payload, headers=h)
    assert r.status_code == 200, r.text
    lid = r.json()['id']
    again = client.post('/api/knowledge/links', json={'source_id': b, 'target_id': a}, headers=h)
    assert again.status_code == 200 and again.json()['created'] is False
    data = client.get('/api/knowledge/graph').json()
    assert sum(n['label'] == 'bandung' for n in data['nodes']) == 1
    assert any(e['kind'] == 'owner_link' and e['link_id'] == lid and e['confirmed'] for e in data['edges'])
    assert any(e['kind'] == 'lexical' and e['term'] == 'bandung' for e in data['edges'])
    assert all(e['evidence'] for e in data['edges'])
    assert client.delete(f'/api/memories/{a}', headers=h).status_code == 200
    after = client.get('/api/knowledge/graph').json()
    assert all(n['id'] != f'memory:{a}' for n in after['nodes'])
    assert all(e.get('link_id') != lid for e in after['edges'])
    assert not any(n['label'] == 'bakso' for n in after['nodes'])


def test_secret_denied_no_note_or_chat_record(client):
    h = login(client)
    r = client.post('/api/chat', json={'message': 'Ingat password saya abcdef123456'}, headers=h)
    assert r.status_code == 422
    assert client.get('/api/memories').json()['total'] == 0
    assert client.get('/api/history').json()['messages'] == []


def test_commit_failure_never_confirms_save(client, monkeypatch):
    h = login(client)
    from sqlalchemy.orm import Session
    def broken_commit(self):
        raise SQLAlchemyError('synthetic failure')
    monkeypatch.setattr(Session, 'commit', broken_commit)
    r = client.post('/api/memories', json={'text': 'This must not persist'}, headers=h)
    assert r.status_code == 503
    assert 'saved' not in r.json()


def test_legacy_notes_retained_and_duplicate_not_rewritten(client):
    h = login(client)
    with session_factory()() as db:
        n = MemoryNote(content='Existing legacy note')
        db.add(n); db.commit(); mid = n.id
    r = client.post('/api/memories', json={'text': 'Existing legacy note'}, headers=h)
    assert r.status_code == 200 and r.json()['id'] == mid and r.json()['created'] is False
    assert client.get('/api/memories').json()['memories'][0]['source'] == 'legacy_memory'


def test_model_receives_persistent_memory_as_reference(client, monkeypatch):
    h = login(client)
    client.post('/api/memories', json={'text': 'Saya suka bakso'}, headers=h)
    monkeypatch.setenv('OPENAI_API_KEY', 'unit-test-placeholder')
    import sonic.brain as brain
    requests = []
    class Reply:
        status_code = 200
        def json(self):
            return {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Anda suka bakso [memory 1].'}]}]}
    class MockClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            requests.append(copy.deepcopy(kwargs['json'])); return Reply()
    monkeypatch.setattr(brain.httpx, 'AsyncClient', MockClient)
    r = client.post('/api/chat', json={'message': 'Apa makanan yang saya suka?'}, headers=h)
    assert r.status_code == 200
    assert 'saya suka bakso' in requests[0]['input'][0]['content'].lower()
    assert 'UNTRUSTED REFERENCE DATA' in requests[0]['input'][0]['content']
    assert 'memory_save' not in [t['name'] for t in requests[0]['tools']]
    assert r.json()['memory_events'] == []


def test_negation_denies_tool_even_when_model_requests_it(client):
    login(client)
    from sonic.brain import run_tool
    with session_factory()() as db:
        r = run_tool(db, 'memory_save', {'fact': 'I like bakso'}, 'Jangan ingat bahwa saya suka bakso')
        assert r['error'] == 'MEMORY_REQUIRES_EXPLICIT_USER_REQUEST'
        assert db.scalar(select(func.count()).select_from(MemoryNote)) == 0


def test_memory_validation_link_removal_and_sql_wildcards(client):
    h = login(client)
    for text in ['    ', 'api key: not-real', 'password hidden']:
        assert client.post('/api/memories', json={'text': text}, headers=h).status_code == 422
    a = client.post('/api/memories', json={'text': 'Bakso adalah favorit'}, headers=h).json()['id']
    b = client.post('/api/memories', json={'text': 'Bandung adalah lokasi'}, headers=h).json()['id']
    assert client.post('/api/knowledge/links', json={'source_id': a, 'target_id': a}, headers=h).status_code == 422
    assert client.post('/api/knowledge/links', json={'source_id': a, 'target_id': 999999}, headers=h).status_code == 404
    r = client.post('/api/knowledge/links', json={'source_id': a, 'target_id': b}, headers=h)
    lid = r.json()['id']
    assert client.delete(f'/api/knowledge/links/{lid}', headers=h).json()['deleted']
    assert client.delete(f'/api/knowledge/links/{lid}', headers=h).status_code == 404
    with session_factory()() as db:
        assert not search_notes(db, 'unknown_%term')
