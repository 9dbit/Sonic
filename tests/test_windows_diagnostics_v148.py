"""Bounded Windows diagnostics contracts, no arbitrary command execution."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("windows_diagnostics_v148",ROOT/"scripts/windows_diagnostics_v148.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def test_unknown_action_never_executes(monkeypatch):
    with pytest.raises(PermissionError):
        m.run("powershell.exec")
    with pytest.raises(PermissionError):
        m.run("diagnostics.scan.ports")

def test_clock_has_explicit_ntp_uncertainty(monkeypatch):
    monkeypatch.setattr(m,"os",SimpleNamespace(name="nt"))
    result=m.run("diagnostics.clock")
    assert result["read_only"] is True
    assert result["result"]["ntp_verified"] is False
    assert "observed_at" in result["result"]

def test_ping_uses_only_fixed_targets(monkeypatch):
    calls=[]
    def fake_run(cmd,**kwargs):
        calls.append((cmd,kwargs))
        return SimpleNamespace(returncode=0,stdout="Reply from 1.1.1.1: bytes=32 time=2ms TTL=57\n")
    monkeypatch.setattr(m.subprocess,"run",fake_run)
    result=m._ping()
    assert len(calls)==2
    assert [c[0][-1] for c in calls]==["1.1.1.1","8.8.8.8"]
    assert all(c[1]["shell"] is False for c in calls)
    assert all(c[1]["timeout"] <= 7 for c in calls)
    assert result["targets"][0]["reachable"] is True

def test_event_collection_has_no_messages(monkeypatch):
    monkeypatch.setattr(m,"_powershell",lambda *args,**kwargs: '{"Id":42,"ProviderName":"TestProvider","Message":"my password"}')
    events=m._events()
    assert events["system_errors_last_24h_sample"]==[{"id":42,"provider":"TestProvider"}]
    assert "password" not in str(events)
    assert events["message_text_collected"] is False
