"""Authorized Companion local one-shot pairing request QA, no credentials read."""
import importlib, json, sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
mod=importlib.import_module("windows_pairing_v151")
BASE="https://sonic-web-staging.up.railway.app"
URL=BASE+"/#sonic-pair="+"A"*43


def test_no_local_request_does_not_call_cloud(tmp_path):
    def forbidden(*_):
        raise AssertionError("No cloud API call without an authorized local flag")
    assert mod.process(tmp_path,BASE,forbidden,now=1000)=={"issued":False}
    assert not (tmp_path/"state"/mod.RESULT).exists()


def test_one_shot_issue_and_expiry_cleanup(tmp_path):
    state=tmp_path/"state";state.mkdir()
    (state/mod.FLAG).write_bytes(b"")
    calls=[]
    def api(route,data):
        calls.append((route,data))
        return {"pair_url":URL,"expires_in_seconds":900,"one_time":True}
    outcome=mod.process(tmp_path,BASE,api,now=1000)
    assert outcome=={"issued":True,"expires_in_seconds":900}
    assert calls==[("/api/preview/trusted/issue",{})]
    assert not (state/mod.FLAG).exists()
    saved=json.loads((state/mod.RESULT).read_text())
    assert saved=={"pair_url":URL,"expires_at_epoch":1900}
    assert URL not in str(outcome)  # never echoed to agent logs
    assert mod.process(tmp_path,BASE,api,now=1001)=={"issued":False}
    assert len(calls)==1
    assert mod.process(tmp_path,BASE,api,now=1900)=={"issued":False}
    assert not (state/mod.RESULT).exists()


def test_foreign_or_malformed_pairing_url_rejected(tmp_path):
    state=tmp_path/"state";state.mkdir()
    (state/mod.FLAG).write_bytes(b"")
    with pytest.raises(RuntimeError,match="INVALID_PAIRING_URL_ORIGIN"):
        mod.process(tmp_path,BASE,lambda *_:{"pair_url":"https://attacker.invalid/#sonic-pair=bad",
                                            "expires_in_seconds":900})
    assert not (state/mod.FLAG).exists()
    assert not (state/mod.RESULT).exists()


def test_failed_issue_must_not_retry_automatically(tmp_path):
    state=tmp_path/"state";state.mkdir()
    (state/mod.FLAG).write_bytes(b"")
    count=[]
    def failing(*_):
        count.append(True)
        raise ConnectionError("synthetic offline")
    with pytest.raises(ConnectionError):
        mod.process(tmp_path,BASE,failing)
    assert len(count)==1
    assert mod.process(tmp_path,BASE,failing)=={"issued":False}
    assert len(count)==1
