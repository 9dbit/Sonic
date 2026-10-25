#!/usr/bin/env python3
"""SONIC 0.5 Windows companion: telemetry plus explicitly approved, local-allowlisted actions.

No inbound ports, admin rights, trading access or unrestricted command execution.
Local requirements: Windows desktop, owner account, compatible Python 3.12.
"""
from __future__ import annotations
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
DEVICE=os.environ.get('SONIC_DEVICE_ID','TRADEVICEPC')
BASE=os.environ.get('SONIC_BASE_URL','').rstrip('/')
TOKEN=os.environ.get('SONIC_DEVICE_TOKEN','')
ALLOWED_ROOT=Path(os.environ.get('SONIC_WORKSPACE_ROOT','D:/Sonic/work')).resolve(strict=False)
RECIPES={
    'clock':'Get-Date -Format o',
    'memory':'Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress',
    'system':'[ordered]@{Computer=$env:COMPUTERNAME;OS=[Environment]::OSVersion.VersionString;CPUCount=[Environment]::ProcessorCount} | ConvertTo-Json -Compress',
}
KEYS={'ENTER':0x0d,'TAB':0x09,'BACKSPACE':0x08,'DELETE':0x2e,'LEFT':0x25,'RIGHT':0x27,'UP':0x26,'DOWN':0x28,'HOME':0x24,'END':0x23,'ESCAPE':0x1b}


def ensure_config():
    if os.name!='nt' or not BASE.startswith('https://') or len(TOKEN)<32 or not ALLOWED_ROOT.is_dir():
        raise RuntimeError('Windows, HTTPS, device credential and workspace root are required')


def api(route,payload):
    data=json.dumps(payload,separators=(',',':')).encode()
    request=Request(BASE+route,data=data,method='POST',headers={'Authorization':'Bearer '+TOKEN,
                     'Content-Type':'application/json','Accept':'application/json'})
    with urlopen(request,timeout=12) as response:
        if response.status!=200:raise RuntimeError('Unexpected HTTP response')
        return json.loads(response.read(32768))


def stats():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),
                  ('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),
                  ('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),
                  ('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),
                  ('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
    s=MEMORYSTATUSEX();s.dwLength=ctypes.sizeof(s)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
        raise OSError('GlobalMemoryStatusEx unavailable')
    disks=[]
    for letter in 'CD':
        root=letter+':\\'
        if os.path.isdir(root):
            try:
                import shutil
                usage=shutil.disk_usage(root)
                disks.append({'drive':letter+':','total_bytes':usage.total,'free_bytes':usage.free})
            except OSError:pass
    kernel32=ctypes.windll.kernel32
    kernel32.GetTickCount64.restype=ctypes.c_ulonglong
    return {'ram_total_bytes':int(s.ullTotalPhys),'ram_available_bytes':int(s.ullAvailPhys),
            'ram_used_percent':int(s.dwMemoryLoad),'uptime_seconds':int(kernel32.GetTickCount64()/1000),
            'logical_cpu_count':os.cpu_count() or 1,'disks':disks}


def notepad_foreground(hwnd_text):
    """Require the current foreground HWND to belong to real Notepad.

    Win32 function signatures are explicitly pointer-width-safe on 64-bit Windows.
    """
    from ctypes import wintypes
    if not isinstance(hwnd_text,str) or not hwnd_text.isdecimal():
        raise ValueError('WINDOW_INVALID')
    user32=ctypes.windll.user32
    kernel32=ctypes.windll.kernel32
    user32.IsWindow.argtypes=[wintypes.HWND];user32.IsWindow.restype=wintypes.BOOL
    user32.GetForegroundWindow.argtypes=[];user32.GetForegroundWindow.restype=wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype=wintypes.DWORD
    kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel32.OpenProcess.restype=wintypes.HANDLE
    kernel32.CloseHandle.argtypes=[wintypes.HANDLE];kernel32.CloseHandle.restype=wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype=wintypes.BOOL
    hwnd=int(hwnd_text)
    if not 0<hwnd<2**(8*ctypes.sizeof(ctypes.c_void_p)) or not user32.IsWindow(hwnd) or user32.GetForegroundWindow()!=hwnd:
        raise PermissionError('NOTEPAD_NOT_FOREGROUND')
    pid=wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid)) or not pid.value:
        raise PermissionError('TARGET_PROCESS_UNAVAILABLE')
    process=kernel32.OpenProcess(0x1000,False,pid.value)
    if not process:raise PermissionError('TARGET_PROCESS_DENIED')
    try:
        length=wintypes.DWORD(32768)
        path=ctypes.create_unicode_buffer(32768)
        if not kernel32.QueryFullProcessImageNameW(process,0,path,ctypes.byref(length)) or Path(path.value).name.casefold()!='notepad.exe':
            raise PermissionError('NOTEPAD_ONLY')
    finally:kernel32.CloseHandle(process)
    if user32.GetForegroundWindow()!=hwnd:raise PermissionError('TARGET_CHANGED')
    return hwnd


def keypress(vk):
    from ctypes import wintypes
    user32=ctypes.windll.user32
    user32.keybd_event.argtypes=[wintypes.BYTE,wintypes.BYTE,wintypes.DWORD,ctypes.c_size_t]
    user32.keybd_event.restype=None
    user32.keybd_event(vk,0,0,0);time.sleep(.012);user32.keybd_event(vk,0,2,0)


def unicode_type(value):
    """Send UTF-16 Unicode to Notepad without using clipboard, paste, or shell."""
    from ctypes import wintypes
    ulong_ptr=ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p)==8 else ctypes.c_uint32
    class MOUSEINPUT(ctypes.Structure):
        _fields_=[('dx',wintypes.LONG),('dy',wintypes.LONG),('mouseData',wintypes.DWORD),
                  ('dwFlags',wintypes.DWORD),('time',wintypes.DWORD),('dwExtraInfo',ulong_ptr)]
    class KEYBDINPUT(ctypes.Structure):
        _fields_=[('wVk',wintypes.WORD),('wScan',wintypes.WORD),('dwFlags',wintypes.DWORD),
                  ('time',wintypes.DWORD),('dwExtraInfo',ulong_ptr)]
    class HARDWAREINPUT(ctypes.Structure):
        _fields_=[('uMsg',wintypes.DWORD),('wParamL',wintypes.WORD),('wParamH',wintypes.WORD)]
    class INPUT_UNION(ctypes.Union):
        _fields_=[('mi',MOUSEINPUT),('ki',KEYBDINPUT),('hi',HARDWAREINPUT)]
    class INPUT(ctypes.Structure):
        _fields_=[('type',wintypes.DWORD),('u',INPUT_UNION)]
    user32=ctypes.windll.user32
    user32.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(INPUT),ctypes.c_int]
    user32.SendInput.restype=wintypes.UINT
    data=value.encode('utf-16-le')
    for offset in range(0,len(data),2):
        code=int.from_bytes(data[offset:offset+2],'little')
        for flags in (0x0004,0x0004|0x0002):
            item=INPUT(type=1,u=INPUT_UNION(ki=KEYBDINPUT(0,code,flags,0,0)))
            if user32.SendInput(1,ctypes.byref(item),ctypes.sizeof(INPUT))!=1:
                raise OSError('INPUT_NOT_ACCEPTED')


def list_workspace(path):
    target=Path(path).resolve(strict=True)
    if target != ALLOWED_ROOT and ALLOWED_ROOT not in target.parents:
        raise PermissionError('WORKSPACE_ONLY')
    if not target.is_dir(): raise PermissionError('DIRECTORY_REQUIRED')
    from itertools import islice
    sampled=sorted(islice(target.iterdir(),61),key=lambda p:p.name.casefold())
    files=[]
    for entry in sampled[:60]:
        if any(fragment in entry.name.casefold() for fragment in ('secret','password','.env','token','credential')):
            continue
        if entry.is_symlink():continue
        try:
            files.append({'name':entry.name[:100],'kind':'directory' if entry.is_dir() else 'file',
                          'bytes':min(entry.stat().st_size,2**46) if entry.is_file() else None})
        except (PermissionError,OSError):continue
    return {'directory':str(target),'items':files,'truncated':len(sampled)>60}


def list_processes():
    import csv,io
    # No command line, executable path, environment, security tokens or elevation.
    out=subprocess.run(['tasklist.exe','/FO','CSV','/NH'],capture_output=True,text=True,errors='replace',
                       encoding='utf-8-sig',timeout=6,shell=False)
    if out.returncode:raise RuntimeError('TASKLIST_FAILED')
    items=[]
    for row in csv.reader(io.StringIO(out.stdout)):
        if len(row)>=2 and row[1].isdigit():items.append({'process':row[0][:85],'pid':int(row[1])})
        if len(items)>=70:break
    return {'processes':items,'truncated':len(items)>=70}


def list_windows():
    from ctypes import wintypes
    user=ctypes.windll.user32
    user.IsWindowVisible.argtypes=[wintypes.HWND];user.IsWindowVisible.restype=wintypes.BOOL
    user.GetWindowTextLengthW.argtypes=[wintypes.HWND];user.GetWindowTextLengthW.restype=ctypes.c_int
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int];user.GetWindowTextW.restype=ctypes.c_int
    result=[];callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def callback(hwnd,_):
        if len(result)>=40:return False
        if not user.IsWindowVisible(hwnd):return True
        length=user.GetWindowTextLengthW(hwnd)
        if not 1<=length<=512:return True
        buf=ctypes.create_unicode_buffer(length+1)
        if user.GetWindowTextW(hwnd,buf,length+1):
            name=buf.value.strip()
            if name:result.append({'window':str(hwnd),'title':name[:130]})
        return True
    user.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
    user.EnumWindows.restype=wintypes.BOOL
    user.EnumWindows(callback_type(callback),0)
    return {'windows':result,'truncated':len(result)>=40}


def execute(action,params):
    if action=='file.list':return list_workspace(params.get('path',''))
    if action=='process.list':return list_processes()
    if action=='window.list':return list_windows()
    if action=='shell.run':
        recipe=params.get('recipe')
        if recipe not in RECIPES:raise PermissionError('SHELL_RECIPE_NOT_ALLOWED')
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',RECIPES[recipe]],
                         timeout=5,capture_output=True,text=True,encoding='utf-8',errors='replace',shell=False)
        return {'exit_code':p.returncode,'output':p.stdout[:6000],'stderr':p.stderr[:500]}
    if action=='file.read':
        target=Path(params.get('path','')).resolve(strict=True)
        if target==ALLOWED_ROOT or ALLOWED_ROOT not in target.parents:
            raise PermissionError('WORKSPACE_ONLY')
        if not target.is_file() or target.stat().st_size>32768:
            raise PermissionError('TEXT_FILE_LIMIT_32KB')
        if target.suffix.lower() not in {'.txt','.md','.json','.csv','.log','.py','.js','.html','.css'}:
            raise PermissionError('TEXT_TYPES_ONLY')
        if any(term in target.name.lower() for term in ['secret','token','password','.env','key','credential']):
            raise PermissionError('SECRET_FILE_BLOCKED')
        return {'path':str(target),'content':target.read_text(encoding='utf-8-sig')[:16000]}
    if action=='mouse.click':
        hwnd=notepad_foreground(params.get('window'))
        x,y=params.get('x'),params.get('y')
        if type(x) is not int or type(y) is not int or not 0<=x<=16000 or not 0<=y<=16000:
            raise ValueError('INVALID_COORDINATES')
        from ctypes import wintypes
        user32=ctypes.windll.user32
        user32.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype=wintypes.BOOL
        rect=wintypes.RECT()
        if not user32.GetWindowRect(hwnd,ctypes.byref(rect)):raise PermissionError('WINDOW_RECT_UNAVAILABLE')
        if not rect.left<=x<rect.right or not rect.top<=y<rect.bottom:raise PermissionError('OUTSIDE_NOTEPAD_WINDOW')
        notepad_foreground(params.get('window'))
        user32.SetCursorPos(x,y)
        ctypes.windll.user32.mouse_event(0x0002,0,0,0,0)
        ctypes.windll.user32.mouse_event(0x0004,0,0,0,0)
        return {'clicked':True,'target':'notepad.exe'}
    if action in ('keyboard.type','keyboard.key'):
        notepad_foreground(params.get('window'))
        if action=='keyboard.type':
            text=params.get('text')
            if not isinstance(text,str) or not 1<=len(text)<=300 or any(ord(c)<32 for c in text):
                raise ValueError('PRINTABLE_TEXT_ONLY')
            unicode_type(text)
            return {'typed_characters':len(text),'target':'notepad.exe'}
        key=params.get('key')
        if key not in KEYS:raise PermissionError('KEY_NOT_ALLOWED')
        keypress(KEYS[key]);return {'key':key,'target':'notepad.exe'}
    raise ValueError('ACTION_NOT_SUPPORTED')


def system_status():
    return {'hostname':platform.node(),'platform':platform.platform(),'logical_cpu_count':os.cpu_count(),
            'sonic_agent_version':'0.5.0','capabilities':['system.status','system.metrics']}


def run_once():
    m=stats()
    api('/api/device/heartbeat',{'device_id':DEVICE,'hostname':platform.node()[:120],
        'platform':platform.platform()[:200],'agent_version':'0.5.0',
        'capabilities':['system.status','system.metrics','shell.run','file.read','file.list','process.list','window.list','mouse.click','keyboard.type','keyboard.key'],
        'metrics':m,'gui_targets':[]})
    job=api('/api/device/next',{}).get('job')
    if job:
        if job.get('action')=='system.status':
            output=system_status()
            api('/api/device/result',{'device_id':DEVICE,'job_id':job['id'],'success':True,'result':output})
    operator=api('/api/device/operator/next',{}).get('job')
    if operator:
        lease={'request_id':operator['id'],'lease':operator['lease']}
        if api('/api/device/operator/check',lease).get('execute'):
            success=True
            try:result=execute(operator['action'],operator['payload'])
            except (Exception) as ex:
                success=False;result={'error':type(ex).__name__,'detail':str(ex)[:160]}
            api('/api/device/operator/result',{**lease,'success':success,'result':result})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    ensure_config()
    while True:
        try:run_once()
        except (HTTPError,URLError,TimeoutError,ValueError,RuntimeError) as error:
            print('SONIC companion unavailable:',type(error).__name__,flush=True)
            if args.once:raise
        if args.once:break
        time.sleep(20)


if __name__=='__main__':main()
