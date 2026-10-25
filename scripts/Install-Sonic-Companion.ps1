# SONIC companion update, initiated locally by the device owner.
# Keeps a non-administrator Windows Scheduled Task and no inbound network ports.
# Does not stop/restart Windows or access MetaTrader. Must run as the same Windows
# account that created the DPAPI credential. Without -Install this is a dry run.
param([switch]$Install)
$ErrorActionPreference = 'Stop'
$root = 'D:\Sonic\companion'
$workspace = 'D:\Sonic\work'
$python = 'D:\Sonic\.venv\Scripts\python.exe'
$tokenFile = Join-Path $root 'device-token.dpapi'
$agentSource = Join-Path $PSScriptRoot 'windows_agent_v05.py'
$taskName = 'SONIC Read-only Companion'
foreach ($path in @($root,$workspace,$python,$tokenFile,$agentSource)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing requirement: $path" }
}
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if ($task.Principal.RunLevel -eq 'Highest') { throw 'Refusing elevated task. SONIC must run with Limited privileges.' }
Write-Host 'SONIC companion update preflight OK.'
Write-Host 'Actions: read RAM, disk, bounded workspace files, list processes/windows; approved Notepad GUI and fixed shell recipes.'
Write-Host 'No arbitrary PowerShell, no unrestricted filesystem or administrator access.'
if (-not $Install) {
    Write-Host 'Dry-run only. To install, run this command yourself with -Install.'
    return
}
$destination = Join-Path $root 'windows_agent_v05.py'
$runner = Join-Path $root 'Start-SONIC-Companion-V05.ps1'
$backup = Join-Path $root 'windows_agent_v05.previous.py'
if(Test-Path $destination) { Copy-Item $destination $backup -Force }
Copy-Item $agentSource $destination -Force
@'
$ErrorActionPreference = 'Stop'
$root = 'D:\Sonic\companion'
$tokenFile = Join-Path $root 'device-token.dpapi'
$encrypted = Get-Content $tokenFile -Raw
$secure = ConvertTo-SecureString $encrypted
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:SONIC_DEVICE_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:SONIC_BASE_URL = 'https://sonic-web-staging.up.railway.app'
    $env:SONIC_DEVICE_ID = 'TRADEVICEPC'
    $env:SONIC_WORKSPACE_ROOT = 'D:\Sonic\work'
    & 'D:\Sonic\.venv\Scripts\python.exe' -u (Join-Path $root 'windows_agent_v05.py')
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $secure.Dispose()
    Remove-Item Env:SONIC_DEVICE_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:SONIC_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:SONIC_DEVICE_ID -ErrorAction SilentlyContinue
    Remove-Item Env:SONIC_WORKSPACE_ROOT -ErrorAction SilentlyContinue
}
'@ | Set-Content -LiteralPath $runner -Encoding UTF8
# One-shot HTTPS/credential/metrics check before changing the existing task.
# Test credential is never echoed to logs or stored as plain text in a file.
$encrypted = Get-Content $tokenFile -Raw
$secure = ConvertTo-SecureString $encrypted
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:SONIC_DEVICE_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:SONIC_BASE_URL = 'https://sonic-web-staging.up.railway.app'
    $env:SONIC_DEVICE_ID = 'TRADEVICEPC'
    $env:SONIC_WORKSPACE_ROOT = $workspace
    & $python -u $destination --once
    if($LASTEXITCODE -ne 0) { throw 'SONIC telemetry preflight failed: old Scheduled Task preserved' }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $secure.Dispose()
    Remove-Item Env:SONIC_DEVICE_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:SONIC_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:SONIC_DEVICE_ID -ErrorAction SilentlyContinue
    Remove-Item Env:SONIC_WORKSPACE_ROOT -ErrorAction SilentlyContinue
}
$oldAction = $task.Actions
$newAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "' + $runner + '"')
try {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction Stop
    Set-ScheduledTask -TaskName $taskName -Action $newAction -ErrorAction Stop | Out-Null
    Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
    Write-Host 'SONIC telemetry companion installed as Limited user Scheduled Task.'
    Write-Host 'Verify RAM appears within 60 seconds under SONIC Devices.'
} catch {
    Write-Warning 'Install failed, restoring original task action.'
    Set-ScheduledTask -TaskName $taskName -Action $oldAction | Out-Null
    Start-ScheduledTask -TaskName $taskName
    throw
}
