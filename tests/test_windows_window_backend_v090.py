"""Offline Windows Window Control V0.9 checks; NEVER launch or close a real app."""
import ctypes
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import windows_window_v090 as window


@pytest.mark.parametrize('action',('window.open','window.focus','window.close'))
def test_only_exact_allowlist_and_one_app_key(action):
    assert window.validate_action(action,{'app':'metatrader5'})=='metatrader5'
    for payload in ({'app':'chrome'},{'app':'C:/Windows/cmd.exe'},
                    {'app':'metatrader5','force':True},{'app':None},{}):
        with pytest.raises(PermissionError):
            window.validate_action(action,payload)


def test_agent_fails_closed_without_interactive_windows(monkeypatch):
    monkeypatch.setenv('SONIC_WINDOW_CONTROL_ENABLED','1')
    if window.os.name!='nt':
        with pytest.raises(PermissionError,match='WINDOWS_GUI_ONLY'):
            window.require_gui()


def test_meta_trader_launch_requires_local_explicit_exe_path(tmp_path,monkeypatch):
    monkeypatch.delenv('SONIC_MT5_EXE_PATH',raising=False)
    with pytest.raises(PermissionError,match='MT5_LAUNCH_PATH_NOT_CONFIGURED'):
        window._launch_path('metatrader5')
    wrong=tmp_path/'untrusted.exe';wrong.write_bytes(b'test')
    monkeypatch.setenv('SONIC_MT5_EXE_PATH',str(wrong))
    with pytest.raises(PermissionError,match='MT5_EXECUTABLE_NOT_ALLOWLISTED'):
        window._launch_path('metatrader5')
    safe=tmp_path/'terminal64.exe';safe.write_bytes(b'test not an executable')
    monkeypatch.setenv('SONIC_MT5_EXE_PATH',str(safe))
    assert window._launch_path('metatrader5')==safe.resolve()


def test_secret_device_environment_never_enters_launched_app(monkeypatch):
    monkeypatch.setenv('SONIC_DEVICE_TOKEN','fake_secret')
    monkeypatch.setenv('OPENAI_API_KEY','fake_provider_key')
    monkeypatch.setenv('GENERAL_SAFE','expected')
    env=window._safe_env()
    assert 'SONIC_DEVICE_TOKEN' not in env
    assert 'OPENAI_API_KEY' not in env
    assert env['GENERAL_SAFE']=='expected'


def test_multiple_meta_trader_windows_are_ambiguous(monkeypatch):
    monkeypatch.setattr(window,'require_gui',lambda:None)
    monkeypatch.setattr(window,'_window_list',lambda app:[
        {'hwnd':101,'pid':111,'name':'terminal64.exe'},
        {'hwnd':102,'pid':112,'name':'terminal64.exe'}])
    with pytest.raises(PermissionError,match='AMBIGUOUS'):
        window.control('window.close',{'app':'metatrader5'})


class FakeCallable:
    def __init__(self,fn):self.fn=fn
    def __call__(self,*args):return self.fn(*args)


def make_fake_win(monkeypatch,post):
    fake=SimpleNamespace(PostMessageW=FakeCallable(post))
    monkeypatch.setattr(window.ctypes,'windll',SimpleNamespace(user32=fake),raising=False)
    return fake


def test_close_uses_wm_close_once_never_terminate_or_send_keys(monkeypatch):
    target={'hwnd':990,'pid':450,'name':'terminal64.exe'}
    events=[]
    monkeypatch.setattr(window,'require_gui',lambda:None)
    monkeypatch.setattr(window,'_verify_target',lambda app,row:events.append('verify'))
    def current(app):
        return [target] if not any(x[0]=='post' for x in events) else []
    monkeypatch.setattr(window,'_window_list',current)
    monkeypatch.setattr(window.time,'sleep',lambda _:None)
    make_fake_win(monkeypatch,lambda hwnd,msg,w,l:events.append(('post',msg)) or True)
    monkeypatch.setattr(window.subprocess,'Popen',lambda *args,**kwargs:
        (_ for _ in ()).throw(AssertionError('No launch in close flow')))
    result=window.control('window.close',{'app':'metatrader5'})
    assert result['closed'] is True
    assert result['method']=='WM_CLOSE'
    assert ('post',window.WM_CLOSE) in events
    assert sum(isinstance(x,tuple) and x[0]=='post' for x in events)==1
    assert 'note' in result and 'not broker order' in result['note']


def test_unsaved_confirm_dialog_means_close_not_verified(monkeypatch):
    target={'hwnd':990,'pid':450,'name':'notepad.exe'}
    monkeypatch.setattr(window,'require_gui',lambda:None)
    monkeypatch.setattr(window,'_verify_target',lambda app,row:None)
    monkeypatch.setattr(window,'_window_list',lambda app:[target])
    monkeypatch.setattr(window.time,'sleep',lambda _:None)
    make_fake_win(monkeypatch,lambda *args:True)
    result=window.control('window.close',{'app':'notepad'})
    assert result['close_requested'] is True
    assert result['closed'] is False


def test_open_only_preconfigured_executable_no_shell(monkeypatch,tmp_path):
    target={'hwnd':90,'pid':555,'name':'terminal64.exe'}
    calls=[]
    windows=iter([[],[target]])
    monkeypatch.setattr(window,'require_gui',lambda:None)
    monkeypatch.setattr(window,'_window_list',lambda app:next(windows))
    monkeypatch.setattr(window,'_foreground',lambda app,row:True)
    monkeypatch.setattr(window.time,'sleep',lambda _:None)
    candidate=tmp_path/'terminal64.exe';candidate.write_bytes(b'fake')
    monkeypatch.setattr(window,'_launch_path',lambda app:candidate)
    monkeypatch.setattr(window,'_safe_env',lambda:{'PATH':'safe'})
    monkeypatch.setattr(window.subprocess,'Popen',lambda argv,**kwargs:
        calls.append((argv,kwargs)) or SimpleNamespace(pid=123))
    r=window.control('window.open',{'app':'metatrader5'})
    assert r['opened'] is True and r['new_process_started'] is True
    assert len(calls)==1 and calls[0][0]==[str(candidate)]
    assert calls[0][1]['shell'] is False and calls[0][1]['env']=={'PATH':'safe'}
