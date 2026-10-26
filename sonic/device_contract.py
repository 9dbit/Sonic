"""SONIC PC tool validation. No arbitrary commands, process access or secret scanning."""
import math
import re
from typing import Any

ACTIONS = frozenset({'file.mkdir', 'shell.run', 'file.read', 'mouse.click', 'keyboard.type', 'keyboard.key', 'file.list', 'process.list', 'window.list', 'shell.inspect', 'powershell.exec', 'process.terminate'})
RECIPES = {
    'clock': 'Get-Date -Format o',
    'memory': 'Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress',
    'system': '[ordered]@{Computer=$env:COMPUTERNAME;OS=[Environment]::OSVersion.VersionString;CPUCount=[Environment]::ProcessorCount} | ConvertTo-Json -Compress',
}
KEYS = frozenset({'ENTER', 'TAB', 'BACKSPACE', 'DELETE', 'LEFT', 'RIGHT', 'UP', 'DOWN', 'HOME', 'END', 'ESCAPE'})


# Parse, never evaluate, owner supplied diagnostic commands. Both server and PC enforce this grammar.
INSPECTION_ONLY = frozenset({
    'Get-Process', 'Get-Service', 'Get-NetAdapter', 'Get-NetIPConfiguration',
    'Get-NetTCPConnection', 'Get-Volume', 'Get-Disk', 'Get-PhysicalDisk',
    'Get-ScheduledTask', 'Get-HotFix', 'Get-Date'
})
CIM_CLASSES = frozenset({
    'Win32_OperatingSystem', 'Win32_Processor', 'Win32_ComputerSystem',
    'Win32_LogicalDisk', 'Win32_ComputerSystemProduct', 'Win32_VideoController'
})
NAME_RE = re.compile(r'^[A-Za-z0-9_.-]{1,56}' + chr(36))


def parse_inspection(command: str) -> list[str]:
    if not isinstance(command, str) or not 3 <= len(command) <= 160:
        raise ValueError('INSPECTION_COMMAND_INVALID')
    words = command.strip().split()
    if len(words) == 1 and words[0] in INSPECTION_ONLY:
        return words
    if len(words) == 2 and words[0] == 'Get-CimInstance' and words[1] in CIM_CLASSES:
        return words
    if len(words) == 3 and words[0] in ('Get-Process','Get-Service') and words[1] == '-Name' and NAME_RE.fullmatch(words[2]):
        return words
    if len(words) == 3 and words[0] == 'Get-Process' and words[1] == '-Id' and words[2].isdecimal() and 0 < int(words[2]) < 2**31:
        return words
    if len(words) == 3 and words[0] == 'Get-NetTCPConnection' and words[1] == '-State' and words[2] in ('Established','Listen','TimeWait','CloseWait'):
        return words
    raise ValueError('INSPECTION_ONLY')


def validate_powershell_command(command: str, timeout_seconds: int) -> str:
    """Bounded raw PowerShell, allowed only after the separate owner approval gate.

    This is NOT a PowerShell security sandbox. The companion runs as a limited
    Windows user and the owner must approve the exact script before execution.
    """
    if not isinstance(command, str) or not 1 <= len(command.strip()) <= 1200:
        raise ValueError('POWERSHELL_COMMAND_LENGTH')
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ValueError('POWERSHELL_TIMEOUT_RANGE')
    if command.count('\n') > 12 or any(ord(ch) < 32 and ch not in '\r\n\t' for ch in command):
        raise ValueError('POWERSHELL_CONTROL_CHARACTERS')
    if re.search(r'(?i)(SONIC_DEVICE_TOKEN|device-token\.dpapi|SONIC_OWNER_TOKEN|SONIC_SESSION_SECRET|OPENAI_API_KEY|DATABASE_URL)', command):
        raise ValueError('POWERSHELL_SECRET_ACCESS_REFUSED')
    if re.search(r'(?i)(-EncodedCommand|Set-ExecutionPolicy|Start-Process\s+[^\n]*-Verb\s+RunAs)', command):
        raise ValueError('POWERSHELL_ELEVATION_REFUSED')
    return command.strip()



WINDOWS_RESERVED = frozenset({'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))})

def clean_workspace_folder(raw: str) -> str:
    """Only relative paths below the already-authorized SONIC workspace.

    Prevent Windows absolute paths, traversal, alternate streams, device names,
    environment expansion and accidental writes into credential directories.
    """
    if not isinstance(raw,str) or not 1 <= len(raw.strip()) <= 180:
        raise ValueError('FOLDER_NAME_REQUIRED')
    raw=raw.strip().replace('\\','/')
    if raw.startswith(('/', '~')) or re.match(r'^[A-Za-z]:',raw) or raw.startswith('//'):
        raise ValueError('WORKSPACE_RELATIVE_ONLY')
    parts=raw.split('/')
    if len(parts)>5 or any(not 1<=len(p)<=70 for p in parts):
        raise ValueError('FOLDER_DEPTH_OR_LENGTH')
    for p in parts:
        if p in ('.','..') or p[-1] in (' ','.'):
            raise ValueError('FOLDER_TRAVERSAL_OR_TRAILING_DOT')
        if any(ord(ch)<32 or ch in '<>:"|?*' for ch in p) or '
    if action not in ACTIONS or not isinstance(payload, dict):
        raise ValueError('ACTION_NOT_ALLOWED')
    fields = {'shell.run': {'recipe'}, 'file.read': {'path'}, 'mouse.click': {'window', 'x', 'y'},
              'keyboard.type': {'window', 'text'}, 'keyboard.key': {'window', 'key'},
              'file.list': {'path'}, 'file.mkdir': {'path'}, 'process.list': set(), 'window.list': set(), 'shell.inspect': {'command'},
              'powershell.exec': {'command','timeout_seconds'}, 'process.terminate': {'pid','expected_name'}}[action]
    if set(payload) != fields:
        raise ValueError('INVALID_ARGUMENTS')
    if action == 'shell.run' and (not isinstance(payload['recipe'], str) or payload['recipe'] not in RECIPES):
        raise ValueError('SHELL_RECIPE_NOT_ALLOWED')
    if action == 'shell.inspect':
        parse_inspection(payload['command'])
    if action == 'powershell.exec':
        result_command = validate_powershell_command(payload['command'],payload['timeout_seconds'])
        payload = {**payload, 'command': result_command}
    if action == 'process.terminate':
        pid, name = payload['pid'], payload['expected_name']
        if type(pid) is not int or not 4 < pid < 2**31 or not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_. -]{1,100}',name):
            raise ValueError('INVALID_PROCESS_TARGET')
    if action=='file.mkdir':
        return {'path':clean_workspace_folder(payload['path'])}
    if action in ('file.read','file.list'):
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
    """Bounded, typed, non-sensitive Task Manager telemetry. Drop unknown fields."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    numeric = {
        'ram_total_bytes': 2**56, 'ram_available_bytes': 2**56,
        'ram_used_percent': 100, 'swap_total_bytes': 2**56,
        'swap_used_bytes': 2**56, 'uptime_seconds': 2**48,
        'logical_cpu_count': 4096, 'physical_cpu_count': 4096,
        'cpu_usage_percent': 100, 'cpu_frequency_mhz': 100000,
        'disk_read_bytes_per_second': 2**48, 'disk_write_bytes_per_second': 2**48,
        'network_rx_bytes_per_second': 2**48, 'network_tx_bytes_per_second': 2**48,
        'network_rx_bytes': 2**56, 'network_tx_bytes': 2**56,
        'process_count': 1000000, 'service_count': 1000000, 'user_count': 100000,
    }
    for key, maximum in numeric.items():
        value = raw.get(key)
        if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum:
            out[key] = value
    if out.get('ram_available_bytes', 0) > out.get('ram_total_bytes', 2**56):
        out.pop('ram_available_bytes', None)
    if out.get('swap_used_bytes', 0) > out.get('swap_total_bytes', 2**56):
        out.pop('swap_used_bytes', None)
    cores = raw.get('cpu_per_core_percent')
    if isinstance(cores, list):
        out['cpu_per_core_percent'] = [v for v in cores[:64] if type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 100]
    def bounded_number(row, key, maximum=2**56):
        v = row.get(key)
        return v if type(v) in (int, float) and math.isfinite(v) and 0 <= v <= maximum else None
    drives = []
    for row in raw.get('disks', [])[:16] if isinstance(raw.get('disks'), list) else []:
        if not isinstance(row, dict):
            continue
        total = bounded_number(row, 'total_bytes')
        free = bounded_number(row, 'free_bytes')
        if total is None or free is None or free > total:
            continue
        drives.append({'drive': str(row.get('drive', ''))[:24], 'total_bytes': int(total), 'free_bytes': int(free)})
    out['disks'] = drives
    networks = []
    for row in raw.get('network_interfaces', [])[:12] if isinstance(raw.get('network_interfaces'), list) else []:
        if not isinstance(row, dict):
            continue
        d = {'name': str(row.get('name', ''))[:70], 'is_up': row.get('is_up') is True}
        for key in ('speed_mbps', 'rx_bytes_per_second', 'tx_bytes_per_second'):
            value = bounded_number(row, key, 2**48)
            if value is not None:
                d[key] = value
        networks.append(d)
    out['network_interfaces'] = networks
    processes = []
    for row in raw.get('processes', [])[:35] if isinstance(raw.get('processes'), list) else []:
        if not isinstance(row, dict):
            continue
        pid = row.get('pid')
        if type(pid) is not int or not 0 < pid < 2**31:
            continue
        item = {'pid': pid, 'name': str(row.get('name', ''))[:85],
                'status': str(row.get('status', ''))[:30]}
        for key, maximum in (('cpu_percent', 10000), ('ram_bytes', 2**56), ('threads', 1000000)):
            value = bounded_number(row, key, maximum)
            if value is not None:
                item[key] = value
        processes.append(item)
    out['processes'] = processes
    services = []
    for row in raw.get('services', [])[:35] if isinstance(raw.get('services'), list) else []:
        if isinstance(row, dict):
            services.append({'name': str(row.get('name', ''))[:100],
                             'status': str(row.get('status', ''))[:24],
                             'start_type': str(row.get('start_type', ''))[:24]})
    out['services'] = services
    apps = []
    for row in raw.get('startup_apps', [])[:35] if isinstance(raw.get('startup_apps'), list) else []:
        if isinstance(row, dict):
            apps.append({'name': str(row.get('name', ''))[:100],
                         'scope': str(row.get('scope', ''))[:30]})
    out['startup_apps'] = apps
    gpu = []
    for row in raw.get('gpus', [])[:8] if isinstance(raw.get('gpus'), list) else []:
        if not isinstance(row, dict):
            continue
        item = {'name': str(row.get('name', ''))[:110]}
        for key, maximum in (('usage_percent', 100), ('memory_total_bytes', 2**56),
                             ('memory_used_bytes', 2**56), ('temperature_c', 150)):
            value = bounded_number(row, key, maximum)
            if value is not None:
                item[key] = value
        gpu.append(item)
    out['gpus'] = gpu
    capabilities = raw.get('unavailable', [])
    out['unavailable'] = [v[:40] for v in capabilities[:12] if isinstance(v, str)] if isinstance(capabilities, list) else []
    return out
 in p or '%' in p:
            raise ValueError('FOLDER_UNSAFE_CHARACTER')
        if p.split('.')[0].upper() in WINDOWS_RESERVED:
            raise ValueError('WINDOWS_RESERVED_NAME')
        if p.casefold() in ('.git','.ssh','.aws','.config','.venv','secrets','credentials'):
            raise ValueError('PROTECTED_FOLDER_NAME')
    return '/'.join(parts)

def clean_request(action: str, payload: dict) -> dict:
    if action not in ACTIONS or not isinstance(payload, dict):
        raise ValueError('ACTION_NOT_ALLOWED')
    fields = {'shell.run': {'recipe'}, 'file.read': {'path'}, 'mouse.click': {'window', 'x', 'y'},
              'keyboard.type': {'window', 'text'}, 'keyboard.key': {'window', 'key'},
              'file.list': {'path'}, 'process.list': set(), 'window.list': set(), 'shell.inspect': {'command'},
              'powershell.exec': {'command','timeout_seconds'}, 'process.terminate': {'pid','expected_name'}}[action]
    if set(payload) != fields:
        raise ValueError('INVALID_ARGUMENTS')
    if action == 'shell.run' and (not isinstance(payload['recipe'], str) or payload['recipe'] not in RECIPES):
        raise ValueError('SHELL_RECIPE_NOT_ALLOWED')
    if action == 'shell.inspect':
        parse_inspection(payload['command'])
    if action == 'powershell.exec':
        result_command = validate_powershell_command(payload['command'],payload['timeout_seconds'])
        payload = {**payload, 'command': result_command}
    if action == 'process.terminate':
        pid, name = payload['pid'], payload['expected_name']
        if type(pid) is not int or not 4 < pid < 2**31 or not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_. -]{1,100}',name):
            raise ValueError('INVALID_PROCESS_TARGET')
    if action in ('file.read','file.list'):
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
    """Bounded, typed, non-sensitive Task Manager telemetry. Drop unknown fields."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    numeric = {
        'ram_total_bytes': 2**56, 'ram_available_bytes': 2**56,
        'ram_used_percent': 100, 'swap_total_bytes': 2**56,
        'swap_used_bytes': 2**56, 'uptime_seconds': 2**48,
        'logical_cpu_count': 4096, 'physical_cpu_count': 4096,
        'cpu_usage_percent': 100, 'cpu_frequency_mhz': 100000,
        'disk_read_bytes_per_second': 2**48, 'disk_write_bytes_per_second': 2**48,
        'network_rx_bytes_per_second': 2**48, 'network_tx_bytes_per_second': 2**48,
        'network_rx_bytes': 2**56, 'network_tx_bytes': 2**56,
        'process_count': 1000000, 'service_count': 1000000, 'user_count': 100000,
    }
    for key, maximum in numeric.items():
        value = raw.get(key)
        if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum:
            out[key] = value
    if out.get('ram_available_bytes', 0) > out.get('ram_total_bytes', 2**56):
        out.pop('ram_available_bytes', None)
    if out.get('swap_used_bytes', 0) > out.get('swap_total_bytes', 2**56):
        out.pop('swap_used_bytes', None)
    cores = raw.get('cpu_per_core_percent')
    if isinstance(cores, list):
        out['cpu_per_core_percent'] = [v for v in cores[:64] if type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 100]
    def bounded_number(row, key, maximum=2**56):
        v = row.get(key)
        return v if type(v) in (int, float) and math.isfinite(v) and 0 <= v <= maximum else None
    drives = []
    for row in raw.get('disks', [])[:16] if isinstance(raw.get('disks'), list) else []:
        if not isinstance(row, dict):
            continue
        total = bounded_number(row, 'total_bytes')
        free = bounded_number(row, 'free_bytes')
        if total is None or free is None or free > total:
            continue
        drives.append({'drive': str(row.get('drive', ''))[:24], 'total_bytes': int(total), 'free_bytes': int(free)})
    out['disks'] = drives
    networks = []
    for row in raw.get('network_interfaces', [])[:12] if isinstance(raw.get('network_interfaces'), list) else []:
        if not isinstance(row, dict):
            continue
        d = {'name': str(row.get('name', ''))[:70], 'is_up': row.get('is_up') is True}
        for key in ('speed_mbps', 'rx_bytes_per_second', 'tx_bytes_per_second'):
            value = bounded_number(row, key, 2**48)
            if value is not None:
                d[key] = value
        networks.append(d)
    out['network_interfaces'] = networks
    processes = []
    for row in raw.get('processes', [])[:35] if isinstance(raw.get('processes'), list) else []:
        if not isinstance(row, dict):
            continue
        pid = row.get('pid')
        if type(pid) is not int or not 0 < pid < 2**31:
            continue
        item = {'pid': pid, 'name': str(row.get('name', ''))[:85],
                'status': str(row.get('status', ''))[:30]}
        for key, maximum in (('cpu_percent', 10000), ('ram_bytes', 2**56), ('threads', 1000000)):
            value = bounded_number(row, key, maximum)
            if value is not None:
                item[key] = value
        processes.append(item)
    out['processes'] = processes
    services = []
    for row in raw.get('services', [])[:35] if isinstance(raw.get('services'), list) else []:
        if isinstance(row, dict):
            services.append({'name': str(row.get('name', ''))[:100],
                             'status': str(row.get('status', ''))[:24],
                             'start_type': str(row.get('start_type', ''))[:24]})
    out['services'] = services
    apps = []
    for row in raw.get('startup_apps', [])[:35] if isinstance(raw.get('startup_apps'), list) else []:
        if isinstance(row, dict):
            apps.append({'name': str(row.get('name', ''))[:100],
                         'scope': str(row.get('scope', ''))[:30]})
    out['startup_apps'] = apps
    gpu = []
    for row in raw.get('gpus', [])[:8] if isinstance(raw.get('gpus'), list) else []:
        if not isinstance(row, dict):
            continue
        item = {'name': str(row.get('name', ''))[:110]}
        for key, maximum in (('usage_percent', 100), ('memory_total_bytes', 2**56),
                             ('memory_used_bytes', 2**56), ('temperature_c', 150)):
            value = bounded_number(row, key, maximum)
            if value is not None:
                item[key] = value
        gpu.append(item)
    out['gpus'] = gpu
    capabilities = raw.get('unavailable', [])
    out['unavailable'] = [v[:40] for v in capabilities[:12] if isinstance(v, str)] if isinstance(capabilities, list) else []
    return out
