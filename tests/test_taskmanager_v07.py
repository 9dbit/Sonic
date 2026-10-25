"""V0.7 Windows telemetry and shell inspection contract tests."""
import pytest
from sonic.device_contract import clean_request, clean_metrics, parse_inspection
from sonic.voice import limits


@pytest.mark.parametrize('command', [
    'Get-Process', 'Get-Service', 'Get-CimInstance Win32_Processor',
    'Get-Process -Name explorer', 'Get-Process -Id 123',
    'Get-NetTCPConnection -State Listen',
])
def test_valid_diagnostics(command):
    assert clean_request('shell.inspect', {'command': command}) == {'command': command}
    assert parse_inspection(command)


@pytest.mark.parametrize('command', [
    'Restart-Computer', 'Stop-Process -Name explorer',
    'Get-Process; Restart-Computer',
    'Get-Process | Stop-Process',
    'Get-Process $(Get-Date)', 'Get-Process > out.txt',
    'Get-CimInstance Win32_Environment',
    'powershell -enc something', 'Get-Process -Id 0',
])
def test_reject_unsafe_commands(command):
    with pytest.raises(ValueError):
        clean_request('shell.inspect', {'command': command})


def test_task_manager_values_are_bounded():
    raw = {'cpu_usage_percent': 52.4, 'ram_total_bytes': 16 * 2**30,
           'ram_available_bytes': 5 * 2**30, 'disk_read_bytes_per_second': 123.0,
           'network_rx_bytes_per_second': 200.0,
           'process_count': 10,
           'processes': [{'pid': 100,'name':'example.exe','ram_bytes':1_000_000,
                          'cpu_percent':15,'status':'running','command_line':'TOP_SECRET'}],
           'services':[{'name':'Spooler','status':'running','start_type':'auto','secret':'hidden'}],
           'gpus':[{'name':'GPU','usage_percent':45,'password':'hidden'}],
           'unavailable':['gpu_engine']}
    cleaned = clean_metrics(raw)
    assert cleaned['cpu_usage_percent'] == 52.4
    assert cleaned['ram_available_bytes'] == 5 * 2**30
    assert cleaned['processes'][0]['pid'] == 100
    assert 'command_line' not in cleaned['processes'][0]
    assert 'secret' not in cleaned['services'][0]
    assert 'password' not in cleaned['gpus'][0]


def test_invalid_metrics_rejected():
    m = clean_metrics({'cpu_usage_percent':101,'ram_total_bytes':100,
                       'ram_available_bytes':200,
                       'processes':[{'pid':-3},{'pid':2,'name':'ok'}],
                       'network_rx_bytes_per_second':-1})
    assert 'cpu_usage_percent' not in m
    assert 'ram_available_bytes' not in m
    assert len(m['processes']) == 1


def test_voice_daily_quota_can_be_disabled(monkeypatch):
    monkeypatch.setenv('SONIC_VOICE_DAILY_SESSIONS','0')
    assert limits()['daily_session_limit']==0
    monkeypatch.setenv('SONIC_VOICE_MAX_SECONDS','1800')
    assert limits()['max_session_seconds']==1800
