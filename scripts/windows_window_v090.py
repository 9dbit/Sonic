"""SONIC V0.9 Windows GUI controller with independently allowlisted apps.

Runs only inside an explicitly enabled interactive Limited-user companion.
No user-provided executable paths/arguments or command shells. Window close
requests WM_CLOSE, never terminate/kill and never manipulate MT5 positions.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from pathlib import Path

APPS = {
    'notepad': frozenset({'notepad.exe'}),
    'paint': frozenset({'mspaint.exe'}),
    'metatrader5': frozenset({'terminal64.exe', 'terminal.exe'}),
}
METHOD = {'window.open':'FIND_OR_LAUNCH', 'window.focus':'SET_FOREGROUND',
          'window.close':'WM_CLOSE'}
WM_CLOSE = 0x0010
SW_RESTORE = 9


def validate_action(action, params):
    if action not in METHOD or not isinstance(params,dict) or set(params)!={'app'}:
        raise PermissionError('WINDOW_CONTROL_ACTION_DENIED')
    app=params.get('app')
    if not isinstance(app,str) or app not in APPS:
        raise PermissionError('WINDOW_APP_NOT_ALLOWLISTED')
    return app


def require_gui():
    if os.name!='nt':
        raise PermissionError('WINDOWS_GUI_ONLY')
    if os.environ.get('SONIC_WINDOW_CONTROL_ENABLED','').lower() not in ('1','true','yes'):
        raise PermissionError('LOCAL_WINDOW_CONTROL_OPT_IN_REQUIRED')


def _window_list(app):
    """Discover only visible, titled top-level windows from exact app processes."""
    require_gui()
    import psutil
    from ctypes import wintypes
    user=ctypes.windll.user32
    user.EnumWindows.restype=wintypes.BOOL
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    user.IsWindowVisible.restype=wintypes.BOOL
    user.GetWindowTextLengthW.argtypes=[wintypes.HWND]
    user.GetWindowTextLengthW.restype=ctypes.c_int
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetWindowTextW.restype=ctypes.c_int
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype=wintypes.DWORD
    result=[]
    cb_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)

    def consider(hwnd,_):
        if not user.IsWindowVisible(hwnd):return True
        length=user.GetWindowTextLengthW(hwnd)
        if not 1<=length<=256:return True
        pid=wintypes.DWORD(0)
        if not user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid)) or pid.value<=4:
            return True
        try:
            name=psutil.Process(pid.value).name().casefold()
        except (psutil.Error, OSError):
            return True
        if name not in APPS[app]:return True
        title=ctypes.create_unicode_buffer(length+1)
        if not user.GetWindowTextW(hwnd,title,length+1) or not title.value.strip():return True
        # The window caption is only used to reject untitled hidden frames.
        # Do not return sensitive title content or command-line arguments.
        result.append({'hwnd':int(hwnd),'pid':pid.value,'name':name})
        return len(result)<6

    user.EnumWindows(cb_type(consider),0)
    return result


def _unique_window(app):
    matches=_window_list(app)
    if not matches:raise LookupError('WINDOW_NOT_FOUND')
    if len(matches)!=1:raise PermissionError('WINDOW_TARGET_AMBIGUOUS')
    return matches[0]


def _verify_target(app, target):
    """Immediately recheck HWND->PID+executable to reject stale/reused handles."""
    from ctypes import wintypes
    import psutil
    user=ctypes.windll.user32
    hwnd=wintypes.HWND(target['hwnd'])
    user.IsWindow.argtypes=[wintypes.HWND]
    user.IsWindow.restype=wintypes.BOOL
    if not user.IsWindow(hwnd):raise RuntimeError('WINDOW_HANDLE_CHANGED')
    pid=wintypes.DWORD(0)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype=wintypes.DWORD
    user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    if pid.value!=target['pid']:
        raise PermissionError('WINDOW_PROCESS_CHANGED')
    try:
        name=psutil.Process(pid.value).name().casefold()
    except (psutil.Error,OSError):
        raise PermissionError('WINDOW_PROCESS_UNAVAILABLE') from None
    if name!=target['name'] or name not in APPS[app]:
        raise PermissionError('WINDOW_EXECUTABLE_CHANGED')


def _foreground(app,target):
    _verify_target(app,target)
    from ctypes import wintypes
    user=ctypes.windll.user32
    hwnd=wintypes.HWND(target['hwnd'])
    user.ShowWindow(hwnd,SW_RESTORE)
    user.SetForegroundWindow.argtypes=[wintypes.HWND]
    user.SetForegroundWindow.restype=wintypes.BOOL
    user.SetForegroundWindow(hwnd)
    user.GetForegroundWindow.restype=wintypes.HWND
    # Windows may deny focus stealing. Report the measured result, not intention.
    return int(user.GetForegroundWindow() or 0)==target['hwnd']


def _launch_path(app):
    if app=='metatrader5':
        raw=os.environ.get('SONIC_MT5_EXE_PATH','')
        if not raw or not Path(raw).is_absolute():
            raise PermissionError('MT5_LAUNCH_PATH_NOT_CONFIGURED')
        path=Path(raw).resolve(strict=True)
        if path.name.casefold() not in APPS[app] or not path.is_file():
            raise PermissionError('MT5_EXECUTABLE_NOT_ALLOWLISTED')
        return path
    root=Path(os.environ.get('SystemRoot',r'C:\Windows')).resolve(strict=True)
    exe='notepad.exe' if app=='notepad' else 'mspaint.exe'
    path=(root/'System32'/exe).resolve(strict=True)
    if not path.is_file() or path.name.casefold() not in APPS[app]:
        raise PermissionError('SYSTEM_APP_NOT_AVAILABLE')
    return path


def _safe_env():
    blocked=('SONIC_','TOKEN','SECRET','PASSWORD','DATABASE_URL',
             'OPENAI_','RAILWAY_','GITHUB_','CLOUDFLARE_')
    return {k:v for k,v in os.environ.items()
            if not any(part in k.upper() for part in blocked)}


def control(action,params):
    app=validate_action(action,params)
    require_gui()
    if action=='window.focus':
        focused=_foreground(app,_unique_window(app))
        return {'app':app,'method':METHOD[action],'focused':focused}

    if action=='window.close':
        target=_unique_window(app)
        _verify_target(app,target)
        from ctypes import wintypes
        user=ctypes.windll.user32
        user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        user.PostMessageW.restype=wintypes.BOOL
        if not user.PostMessageW(wintypes.HWND(target['hwnd']),WM_CLOSE,0,0):
            raise RuntimeError('WINDOW_CLOSE_MESSAGE_NOT_ACCEPTED')
        closed=False
        for _ in range(12):
            time.sleep(.25)
            # A save/confirmation dialog or another same-app window keeps
            # this unverified. Never click through it or force termination.
            remaining=_window_list(app)
            if not any(row['hwnd']==target['hwnd'] for row in remaining):
                # Do not claim the app completely exited; only this window went away.
                closed=True
                break
        return {'app':app,'method':METHOD[action],
                'close_requested':True,'closed':closed,
                'note':'Window close only, not broker order closure'}

    # Open means focus an existing unique window or launch a predefined app.
    windows=_window_list(app)
    if len(windows)>1:
        raise PermissionError('WINDOW_TARGET_AMBIGUOUS')
    if len(windows)==1:
        _foreground(app,windows[0])
        return {'app':app,'method':METHOD[action],'opened':True,
                'already_running':True,'new_process_started':False}
    path=_launch_path(app)
    proc=subprocess.Popen([str(path)],cwd=str(path.parent),env=_safe_env(),
                          shell=False,close_fds=True)
    for _ in range(16):
        time.sleep(.25)
        windows=_window_list(app)
        if len(windows)==1:
            return {'app':app,'method':METHOD[action],'opened':True,
                    'already_running':False,'new_process_started':True}
        if len(windows)>1:break
    return {'app':app,'method':METHOD[action],'opened':False,
            'launch_requested':True,'new_process_started':True}
