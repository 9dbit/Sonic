"""SONIC V0.8 Windows Command Broker.

Owner-approved PowerShell executes as the existing LIMITED interactive Windows
account, never as SYSTEM/administrator. All traffic is outbound HTTPS via the
already-authenticated companion. This is not an operating-system sandbox:
PowerShell has the access of the Windows user running the agent.
"""
from __future__ import annotations

import base64
import codecs
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

MAX_EVENTS = 48
MAX_OUTPUT = 24576
CRITICAL_PROCESSES = frozenset({
    'system', 'registry', 'smss.exe', 'csrss.exe', 'wininit.exe',
    'services.exe', 'lsass.exe', 'winlogon.exe', 'svchost.exe',
    'dwm.exe', 'msmpeng.exe', 'securityhealthservice.exe',
    'python.exe', 'pythonw.exe', 'powershell.exe', 'pwsh.exe',
    'terminal64.exe', 'metatrader5.exe'
})
SENSITIVE_ENV_PARTS = ('SONIC_', 'TOKEN', 'PASSWORD', 'SECRET', 'DATABASE_URL',
                       'OPENAI_', 'RAILWAY_', 'GITHUB_', 'AWS_', 'CLOUDFLARE_')


def validate_script(command: str, timeout_seconds: int) -> str:
    """Independently validate on Windows even if the cloud API is bypassed."""
    if not isinstance(command, str) or not 1 <= len(command.strip()) <= 1200:
        raise PermissionError('COMMAND_LENGTH_INVALID')
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise PermissionError('TIMEOUT_OUTSIDE_1_60')
    if command.count('\n') > 12 or any(ord(c) < 32 and c not in '\r\n\t' for c in command):
        raise PermissionError('COMMAND_CONTROL_CHARACTER')
    if re.search(r'(?i)(SONIC_DEVICE_TOKEN|device-token\.dpapi|SONIC_OWNER_TOKEN|SONIC_SESSION_SECRET|OPENAI_API_KEY|DATABASE_URL)', command):
        raise PermissionError('AGENT_SECRET_REFERENCE_DENIED')
    if re.search(r'(?i)(-EncodedCommand|Set-ExecutionPolicy|Start-Process\s+[^\n]*-Verb\s+RunAs)',command):
        raise PermissionError('ELEVATION_REFERENCE_DENIED')
    return command.strip()


def limited_environment() -> dict[str, str]:
    """Avoid passing SONIC's bearer credential and cloud API secrets to child processes."""
    return {k:v for k,v in os.environ.items()
            if not any(fragment in k.upper() for fragment in SENSITIVE_ENV_PARTS)}


def stop_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill.exe','/PID',str(proc.pid),'/T','/F'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                           timeout=4,check=False)
        except (OSError,subprocess.TimeoutExpired):
            pass
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass


def terminate_process(pid: int, expected_name: str) -> dict:
    """Task Manager End Task with PID reuse guard and critical-process exclusions."""
    import psutil
    if type(pid) is not int or not 4 < pid < 2**31:
        raise PermissionError('INVALID_PID')
    if not isinstance(expected_name,str) or not re.fullmatch(r'[a-zA-Z0-9_. -]{1,100}',expected_name):
        raise PermissionError('INVALID_EXPECTED_NAME')
    target=psutil.Process(pid)
    real_name=target.name()
    if real_name.casefold()!=expected_name.casefold():
        raise PermissionError('PROCESS_NAME_CHANGED')
    if real_name.casefold() in CRITICAL_PROCESSES:
        raise PermissionError('PROTECTED_PROCESS')
    current=psutil.Process()
    if pid==current.pid or any(parent.pid==pid for parent in current.parents()):
        raise PermissionError('COMPANION_PROCESS_PROTECTED')
    target.terminate()
    try:
        target.wait(timeout=4)
    except psutil.TimeoutExpired:
        raise RuntimeError('PROCESS_STILL_RUNNING')
    return {'terminated':True,'pid':pid,'name':real_name}


def run_powershell(command: str, timeout_seconds: int, device_api, lease: dict,
                   workspace: Path) -> dict:
    """Stream bounded stdout/stderr, poll lease for cancel, kill on timeout or loss of auth.

    device_api(route, payload) is the existing authenticated HTTPS-only client.
    Results contain no copied output: chunks are in the append-only stream.
    """
    source=validate_script(command,timeout_seconds)
    root=Path(workspace).resolve(strict=True)
    if not root.is_dir():
        raise PermissionError('WORKSPACE_REQUIRED')
    # -EncodedCommand encodes only already-approved text and avoids shell quoting.
    # It is not permission escalation: execution uses the current limited user.
    script='[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $OutputEncoding=[Console]::OutputEncoding; '+source
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    args=['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',encoded]
    events=queue.Queue(maxsize=128)
    proc=subprocess.Popen(args,cwd=str(root),env=limited_environment(),
                          stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
                          shell=False,bufsize=0)
    def pump(channel,pipe):
        decoder=codecs.getincrementaldecoder('utf-8')('replace')
        try:
            while True:
                chunk=os.read(pipe.fileno(),512)
                if not chunk:break
                text=decoder.decode(chunk)
                if text:
                    try:events.put_nowait((channel,text))
                    except queue.Full:pass
            tail=decoder.decode(b'',final=True)
            if tail:
                try:events.put_nowait((channel,tail))
                except queue.Full:pass
        except (OSError,ValueError):
            pass
        finally:
            try:pipe.close()
            except OSError:pass
    readers=[]
    for name,pipe in (('stdout',proc.stdout),('stderr',proc.stderr)):
        t=threading.Thread(target=pump,args=(name,pipe),daemon=True)
        t.start();readers.append(t)

    seq=0;total=0;truncated=False;cancelled=False;timed_out=False
    started=time.monotonic();last_check=0.0;done_since=None
    try:
        while True:
            now=time.monotonic()
            if now-started>=timeout_seconds:
                timed_out=True;stop_tree(proc);break
            if now-last_check>=1.0:
                last_check=now
                try:
                    allowed=device_api('/api/device/operator/check',lease).get('execute') is True
                except Exception:
                    allowed=False
                if not allowed:
                    cancelled=True;stop_tree(proc);break
            try:
                channel,text=events.get(timeout=.12)
            except queue.Empty:
                if proc.poll() is not None and all(not t.is_alive() for t in readers):
                    if done_since is None:done_since=now
                    if events.empty():break
                continue
            if not text:continue
            remaining=MAX_OUTPUT-total
            if seq>=MAX_EVENTS-1 or remaining<=0:
                truncated=True
                continue
            text=text[:min(1024,remaining)]
            # Avoid low control codes, but preserve tabs and line breaks.
            text=''.join(c for c in text if ord(c)>=32 or c in '\n\r\t')
            if not text:continue
            total+=len(text);seq+=1
            try:
                response=device_api('/api/device/operator/stream',{
                    **lease,'sequence':seq,'channel':channel,'text':text})
                if response.get('accepted') is not True:
                    raise RuntimeError('STREAM_ACK_FAILED')
            except Exception:
                # Never continue an unobservable command without its owner lease.
                cancelled=True;stop_tree(proc);break
        if proc.poll() is None:
            stop_tree(proc)
        if (truncated or timed_out or cancelled) and seq<MAX_EVENTS:
            message=('Output truncated at 24 KiB or event limit' if truncated else
                     'Execution timeout; PowerShell process tree stopped' if timed_out else
                     'Command cancelled or device authorization unavailable')
            try:
                seq+=1
                device_api('/api/device/operator/stream',{
                    **lease,'sequence':seq,'channel':'system','text':message})
            except Exception:
                pass
    finally:
        if proc.poll() is None:stop_tree(proc)
        for thread in readers:
            thread.join(timeout=.6)

    code=proc.returncode
    return {'exit_code':code,'duration_ms':round((time.monotonic()-started)*1000),
            'events_sent':seq,'output_truncated':truncated,
            'cancelled':cancelled,'timed_out':timed_out}
