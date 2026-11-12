"""Passkey session binding and revocation/login-race regression checks."""
from sqlalchemy import delete
from sonic import auth
from sonic.db import session_factory
from sonic.passkeys import OwnerPasskey
from tests.test_passkeys import pc, enroll, post, assertion, b64


def test_cookie_bound_to_passkey_is_unusable_after_direct_revocation(pc):
    _, cid, _ = enroll(pc)
    cookie = pc.cookies.get(auth.COOKIE)
    signed_body = auth._unb64(cookie.split('.')[0]).decode()
    assert 'passkey_id' in signed_body
    assert pc.get('/api/history').status_code == 200
    with session_factory()() as db:
        db.execute(delete(OwnerPasskey).where(OwnerPasskey.credential_id == b64(cid)))
        db.commit()
    assert pc.get('/api/history').status_code == 401


def test_revocation_between_signature_and_cookie_issue_cannot_create_access(pc, monkeypatch):
    private, cid, _ = enroll(pc)
    pc.cookies.clear()
    start = post(pc, 'login/options').json()
    real = auth.issue_session
    def raced(*, passkey_id=None):
        assert passkey_id == b64(cid)
        with session_factory()() as db:
            db.execute(delete(OwnerPasskey).where(OwnerPasskey.credential_id == passkey_id))
            db.commit()
        return real(passkey_id=passkey_id)
    monkeypatch.setattr(auth, 'issue_session', raced)
    result = post(pc, 'login/verify', {'ceremony_id': start['ceremony_id'],
                                     'credential': assertion(start, private, cid)})
    assert result.status_code == 401
    assert not pc.get('/api/session').json()['authenticated']


def test_unsigned_32bit_authenticator_counter_is_supported(pc):
    private, cid, _ = enroll(pc)
    pc.cookies.clear()
    start = post(pc, 'login/options').json()
    result = post(pc, 'login/verify', {'ceremony_id': start['ceremony_id'],
        'credential': assertion(start, private, cid, count=2**32-1)})
    assert result.status_code == 200, result.text
