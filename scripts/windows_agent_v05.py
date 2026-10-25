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
    return {'ram_total_bytes':int(s.ullTotalPhys),'ram_available_bytes':int(s.ullAvailPhys),
            'ram_used_percent':int(s.dwMemoryLoad),'uptime_seconds':int(ctypes.windll.kernel32.GetTickCount64()/1000),
            'logical_cpu_count':os.cpu_count() or 1,'disks':disks}


def notepad_foreground(hwnd_text):
    """Fail closed unless the target HWND is the foreground window of Notepad."""
    if not isinstance(hwnd_text,str) or not hwnd_text.isdecimal():raise ValueError('WINDOW_INVALID')
    user32=ctypes.windll.user32
    hwnd=int(hwnd_text)
    if hwnd<=0 or not user32.IsWindow(hwnd) or user32.GetForegroundWindow()!=hwnd:
        raise PermissionError('NOTEPAD_NOT_FOREGROUND')
    pid=ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    access=0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
    process=ctypes.windll.kernel32.OpenProcess(access,False,pid.value)
    if not process:raise PermissionError('TARGET_PROCESS_DENIED')
    try:
        length=ctypes.c_ulong(32768)
        path=ctypes.create_unicode_buffer(32768)
        ok=ctypes.windll.kernel32.QueryFullProcessImageNameW(process,0,path,ctypes.byref(length))
        if not ok or Path(path.value).name.lower()!='notepad.exe':raise PermissionError('NOTEPAD_ONLY')
    finally:ctypes.windll.kernel32.CloseHandle(process)
    return hwnd


def keypress(vk):
    user32=ctypes.windll.user32
    user32.keybd_event(vk,0,0,0);time.sleep(.012);user32.keybd_event(vk,0,2,0)


def unicode_type(s):
    """SendInput Unicode without paste/clipboard, shortcuts or command separators."""
    class KEYBDINPUT(ctypes.Structure):
        _fields_=[('wVk',ctypes.c_ushort),('wScan',ctypes.c_ushort),('dwFlags',ctypes.c_ulong),
                  ('time',ctypes.c_ulong),('dwExtraInfo',ctypes.POINTER(ctypes.c_ulong))]
    class INPUT_UNION(ctypes.Union):_fields_=[('ki',KEYBDINPUT)]
    class INPUT(ctypes.Structure):_fields_=[('type',ctypes.c_ulong),('u',INPUT_UNION)]
    for ch in s:
        for flag in (0x0004,0x0004|0x0002):
            item=INPUT(type=1,u=INPUT_UNION(ki=KEYBDINPUT(0,ord(ch),flag,0,None)))
            if ctypes.windll.user32.SendInput(1,ctypes.byref(item),ctypes.sizeof(INPUT))!=1:
                raise OSError('INPUT_NOT_ACCEPTED')


def execute(action,params):
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
        rect=(ctypes.c_long*4)();ctypes.windll.user32.GetWindowRect(hwnd,rect)
        if not rect[0]<=x<rect[2] or not rect[1]<=y<rect[3]:raise PermissionError('OUTSIDE_NOTEPAD_WINDOW')
        ctypes.windll.user32.SetCursorPos(x,y)
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
        'capabilities':['system.status','system.metrics','shell.run','file.read','mouse.click','keyboard.type','keyboard.key'],
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
