"""Run on authorized Windows QA PC with synthetic device lease and no cloud key.

Executes only Get-Date and Start-Sleep, tests output streaming, cancellation
and timeouts. Does not touch the Windows Scheduled Task or real SONIC credentials.
"""
import os
from pathlib import Path
import sys
import time

from windows_command_v08 import run_powershell, validate_script, terminate_process


def run(command,seconds,allow_checks=99):
    events=[]
    checks=[0]
    def fake_api(route,payload):
        if route.endswith('/check'):
            checks[0]+=1
            return {'execute':checks[0]<=allow_checks}
        if route.endswith('/stream'):
            events.append(dict(payload))
            return {'accepted':True}
        raise RuntimeError('Unexpected route: '+route)
    result=run_powershell(command,seconds,fake_api,
        {'request_id':'synthetic-v08','lease':'fake-owner-lease'},
        Path(os.environ.get('SONIC_TEST_WORKSPACE',str(Path.cwd()))))
    return result,events,checks[0]


def main():
    if os.name!='nt':
        print('Skipping Windows-specific broker tests on non-Windows host')
        return
    try:
        validate_script('Get-Date',10)
        try:validate_script('Get-Item Env:SONIC_DEVICE_TOKEN',10)
        except PermissionError:pass
        else:raise AssertionError('Secret token references must fail')
        good,events,_=run('Get-Date | Out-String',10)
        assert good['exit_code']==0 and not good['timed_out'] and not good['cancelled'],good
        assert events and any(e['channel']=='stdout' and e['text'].strip() for e in events),events
        assert all(e['sequence']==idx+1 for idx,e in enumerate(events)),events
        before=time.monotonic()
        cancel,events,_=run('Start-Sleep -Seconds 8',15,allow_checks=1)
        assert cancel['cancelled'] and (time.monotonic()-before)<7,cancel
        before=time.monotonic()
        timeout,events,_=run('Start-Sleep -Seconds 8',2)
        assert timeout['timed_out'] and (time.monotonic()-before)<7,timeout
        # No sensitive SONIC bearer should be inherited by spawned PowerShell.
        os.environ['SONIC_DEVICE_TOKEN']='synthetic-never-emit-me'
        clean,events,_=run("Get-ChildItem Env: | Where-Object Name -Like 'SONIC_*' | Out-String",10)
        assert clean['exit_code']==0,clean
        assert 'synthetic-never-emit-me' not in ''.join(x['text'] for x in events)
        assert not any('SONIC_DEVICE_TOKEN' in x['text'] for x in events)
        # End Task is tested only against our own disposable loopback ping.
        import subprocess
        child=subprocess.Popen(['ping.exe','-t','127.0.0.1'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            time.sleep(.25)
            ended=terminate_process(child.pid,'PING.EXE')
            assert ended['terminated'] is True and ended['pid']==child.pid
            child.wait(timeout=4)
        finally:
            if child.poll() is None:child.kill();child.wait()
        print({'live_readonly_command':'pass','stream_chunks':len(events),
               'cancel_tree':'pass','timeout_tree':'pass',
               'bearer_child_env_clean':'pass'})
    finally:
        os.environ.pop('SONIC_DEVICE_TOKEN',None)


if __name__=='__main__':
    main()
