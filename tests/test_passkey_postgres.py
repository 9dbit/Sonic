"""Disposable PostgreSQL proof for atomic challenges and first-enrollment races.

Runs only against an explicitly named local CI database in a unique schema.
Never consumes DATABASE_URL or credentials from a live deployment.
"""
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from sonic import auth
from sonic.db import Base, session_factory, utcnow
from sonic.passkeys import OwnerPasskey, PasskeyChallenge, _consume
from tests.test_passkeys import ORIGIN, SETUP, assertion, b64, enroll, key, post, registration


@pytest.fixture
def pg_client(monkeypatch):
    raw = os.environ.get('SONIC_PASSKEY_TEST_POSTGRES_URL', '')
    if not raw:
        pytest.skip('Dedicated disposable PostgreSQL URL not configured')
    url = make_url(raw)
    if url.host not in ('localhost', '127.0.0.1') or url.database != 'sonic_passkey_ci':
        raise RuntimeError('Refusing non-local or non-CI PostgreSQL target')
    import sonic.db as storage
    from sonic.api import app
    schema = 'passkey_ci_' + uuid.uuid4().hex
    admin = create_engine(raw)
    with admin.begin() as connection:
        connection.execute(text('CREATE SCHEMA "' + schema + '"'))
    engine = create_engine(raw, connect_args={'options': '-csearch_path=' + schema}, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv('SONIC_PASSWORDLESS_LOGIN', 'true')
    monkeypatch.setenv('SONIC_ENV', 'local')
    monkeypatch.setenv('SONIC_PUBLIC_URL', ORIGIN)
    monkeypatch.setenv('SONIC_OWNER_TOKEN_SHA256', auth.sha256('synthetic-owner-only'))
    monkeypatch.setenv('SONIC_SESSION_SECRET', 'synthetic-session-' * 5)
    monkeypatch.setenv('SONIC_PASSKEY_ENROLLMENT_SHA256', auth.sha256(SETUP))
    monkeypatch.setenv('SONIC_PASSKEY_ENROLLMENT_EXPIRES', str(int(time.time()) + 600))
    for name in ('DATABASE_URL', 'RAILWAY_ENVIRONMENT_NAME', 'OPENAI_API_KEY', 'DEEPSEEK_API_KEY', 'OPENROUTER_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    previous_engine, previous_factory = storage._engine, storage._Session
    storage._engine, storage._Session = engine, sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with TestClient(app, base_url=ORIGIN) as client:
            yield client
    finally:
        storage._engine, storage._Session = previous_engine, previous_factory
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
        admin.dispose()


def test_postgres_actual_signature_and_uint32_counter(pg_client):
    private, credential_id, _ = enroll(pg_client)
    pg_client.cookies.clear()
    start = post(pg_client, 'login/options').json()
    result = post(pg_client, 'login/verify', {'ceremony_id': start['ceremony_id'],
        'credential': assertion(start, private, credential_id, count=2**32-1)})
    assert result.status_code == 200, result.text
    assert pg_client.get('/api/history').status_code == 200
    with session_factory()() as db:
        assert db.get(OwnerPasskey, b64(credential_id)).sign_count == 2**32-1


def test_postgres_atomic_challenge_one_winner(pg_client):
    binding, cid = 'B' * 43, 'C' * 30
    with session_factory()() as db:
        db.add(PasskeyChallenge(id=cid, challenge=b64(b'one-challenge'), purpose='login',
            binding=auth.sha256(binding), authority='', expires_at=utcnow() + timedelta(seconds=120)))
        db.commit()
    barrier = Barrier(2)
    def claim(_):
        request = Request({'type': 'http', 'headers': [(b'cookie', ('sonic_passkey_login=' + binding).encode())]})
        with session_factory()() as db:
            barrier.wait(timeout=10)
            try:
                _consume(db, request, cid, 'login', '')
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(claim, range(2))) == [200, 401]


def test_postgres_first_enrollment_race_one_winner(pg_client):
    from sonic.api import app
    barrier = Barrier(2)
    with TestClient(app, base_url=ORIGIN) as other:
        clients = [pg_client, other]
        requests = []
        for client in clients:
            private, cid = key()
            start = post(client, 'register/options', {'enrollment_key': SETUP}).json()
            requests.append({'enrollment_key': SETUP, 'ceremony_id': start['ceremony_id'],
                'credential': registration(start, private, cid)})
        def finish(index):
            barrier.wait(timeout=10)
            return post(clients[index], 'register/verify', requests[index]).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(finish, range(2)))
        assert statuses[0] == 200 and statuses[1] in (403, 409), statuses
        with session_factory()() as db:
            assert len(list(db.scalars(select(OwnerPasskey)))) == 1
