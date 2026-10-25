"""SONIC PC tool validation. No arbitrary commands, process access or secret scanning."""
import math
from typing import Any

ACTIONS = frozenset({'shell.run', 'file.read', 'mouse.click', 'keyboard.type', 'keyboard.key'})
RECIPES = {
    'clock': 'Get-Date -Format o',
    'memory': 'Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress',
    'system': '[ordered]@{Computer=$env:COMPUTERNAME;OS=[Environment]::OSVersion.VersionString;CPUCount=[Environment]::ProcessorCount} | ConvertTo-Json -Compress',
}
KEYS = frozenset({'ENTER', 'TAB', 'BACKSPACE', 'DELETE', 'LEFT', 'RIGHT', 'UP', 'DOWN', 'HOME', 'END', 'ESCAPE'})


def clean_request(action: str, payload: dict) -> dict:
    if action not in ACTIONS or not isinstance(payload, dict):
        raise ValueError('ACTION_NOT_ALLOWED')
    fields = {'shell.run': {'recipe'}, 'file.read': {'path'}, 'mouse.click': {'window', 'x', 'y'},
              'keyboard.type': {'window', 'text'}, 'keyboard.key': {'window', 'key'}}[action]
    if set(payload) != fields:
        raise ValueError('INVALID_ARGUMENTS')
    if action == 'shell.run' and (not isinstance(payload['recipe'], str) or payload['recipe'] not in RECIPES):
        raise ValueError('SHELL_RECIPE_NOT_ALLOWED')
    if action == 'file.read':
        path = payload['path']
        if not isinstance(path, str) or not 1 <= len(path) <= 500 or '\0' in path or path.startswith(('\\\\', '//')):
            raise ValueError('INVALID_PATH')
    if 'window' in fields:
        w = payload['window']
        if not isinstance(w, str) or not w.isdecimal() or not 0 < int(w) < 2**64:
            raise ValueError('INVALID_WINDOW')
    if action == 'mouse.click' and any(type(payload[k]) is not int or not 0 <= payload[k] <= 16000 for k in ('x','y')):
        raise ValueError('INVALID_COORDINATES')
    if action == 'keyboard.type':
        s = payload['text']
        if not isinstance(s,str) or not 1 <= len(s) <= 300 or any(ord(c)<32 for c in s):
            raise ValueError('TEXT_MUST_BE_PRINTABLE')
    result = dict(payload)
    if action == 'keyboard.key':
        k = payload['key']
        if not isinstance(k,str) or k.upper() not in KEYS:
            raise ValueError('KEY_NOT_ALLOWED')
        result['key'] = k.upper()
    return result


def clean_metrics(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in ('ram_total_bytes','ram_available_bytes','ram_used_percent','uptime_seconds','logical_cpu_count'):
        v = raw.get(key)
        if type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 2**56:
            out[key] = v
    if out.get('ram_used_percent',0)>100:out.pop('ram_used_percent',None)
    if out.get('logical_cpu_count',0)>4096:out.pop('logical_cpu_count',None)
    if out.get('ram_available_bytes',0)>out.get('ram_total_bytes',2**56):out.pop('ram_available_bytes',None)
    disks=[]
    for d in raw.get('disks',[])[:8] if isinstance(raw.get('disks'),list) else []:
        if not isinstance(d,dict):continue
        total,free=d.get('total_bytes'),d.get('free_bytes')
        if type(total) is int and type(free) is int and 0<=free<=total<=2**56:
            disks.append({'drive':str(d.get('drive',''))[:20], 'total_bytes':total,'free_bytes':free})
    out['disks']=disks
    return out
