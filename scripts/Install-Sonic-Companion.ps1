# SONIC V0.8 companion deployment. Owner-initiated, no inbound ports and
# no elevation. PowerShell broker must be explicitly opted into with
# -Install -EnablePowerShell and still requires approval in the SONIC browser.
param([switch]$Install, [switch]$EnablePowerShell)
$ErrorActionPreference = 'Stop'
$root = 'D:\Sonic\companion'
$workspace = 'D:\Sonic\work'
$python = 'D:\Sonic\.venv\Scripts\python.exe'
$tokenFile = Join-Path $root 'device-token.dpapi'
$agentSource = Join-Path $PSScriptRoot 'windows_agent_v05.py'
$brokerSource = Join-Path $PSScriptRoot 'windows_command_v08.py'
$workspaceSource = Join-Path $PSScriptRoot 'windows_workspace_v082.py'
$taskName = 'SONIC Read-only Companion'

foreach ($path in @($root,$workspace,$python,$tokenFile,$agentSource,$brokerSource,$workspaceSource)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing requirement: $path" }
}
& $python -c 'import psutil' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'SONIC V0.8 needs psutil in D:\Sonic\.venv' }
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if ($task.Principal.RunLevel -eq 'Highest') { throw 'Refusing elevated task. SONIC must run with Limited privileges.' }
$enableValue = if($EnablePowerShell) { '1' } else { '0' }
Write-Host 'SONIC V0.8 installer / Limited user / outbound HTTPS.'
Write-Host ('PowerShell opt-in: ' + [bool]$EnablePowerShell)
Write-Host 'Owner review and one-time digest confirmation required for every PC command.'
Write-Host 'PowerShell is not a sandbox; commands inherit the Windows user permissions.'
if (-not $Install) {
    Write-Host 'Dry-run only. Use -Install to update. Add -EnablePowerShell to opt in locally.'
    return
}

$stage = Join-Path $workspace 'sonic-v08-install-candidate'
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item -LiteralPath $agentSource -Destination (Join-Path $stage 'windows_agent_v05.py') -Force
Copy-Item -LiteralPath $brokerSource -Destination (Join-Path $stage 'windows_command_v08.py') -Force
Copy-Item -LiteralPath $workspaceSource -Destination (Join-Path $stage 'windows_workspace_v082.py') -Force

# Validate without dequeuing any owner-approved operation.
$encrypted = Get-Content -LiteralPath $tokenFile -Raw
$secure = ConvertTo-SecureString $encrypted
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:SONIC_DEVICE_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:SONIC_BASE_URL = 'https://sonic-web-staging.up.railway.app'
    $env:SONIC_DEVICE_ID = 'TRADEVICEPC'
    $env:SONIC_WORKSPACE_ROOT = $workspace
    $env:SONIC_ENABLE_POWERSHELL_EXEC = $enableValue
    & $python -u (Join-Path $stage 'windows_agent_v05.py') --preflight
    if ($LASTEXITCODE -ne 0) { throw 'SONIC V0.8 preflight failed; old Scheduled Task unchanged' }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $secure.Dispose()
    foreach ($key in @('SONIC_DEVICE_TOKEN','SONIC_BASE_URL','SONIC_DEVICE_ID',
                       'SONIC_WORKSPACE_ROOT','SONIC_ENABLE_POWERSHELL_EXEC')) {
        Remove-Item -Path ('Env:' + $key) -ErrorAction SilentlyContinue
    }
}

$destination = Join-Path $root 'windows_agent_v05.py'
$brokerDest = Join-Path $root 'windows_command_v08.py'
$workspaceDest = Join-Path $root 'windows_workspace_v082.py'
$runner = Join-Path $root 'Start-SONIC-Companion-V08.ps1'
$backup = Join-Path $root 'windows_agent_v05.before_v08.py'
$brokerBackup = Join-Path $root 'windows_command_v08.previous.py'
$workspaceBackup = Join-Path $root 'windows_workspace_v082.previous.py'
if(Test-Path $destination) { Copy-Item -LiteralPath $destination -Destination $backup -Force }
if(Test-Path $brokerDest) { Copy-Item -LiteralPath $brokerDest -Destination $brokerBackup -Force }
if(Test-Path $workspaceDest) { Copy-Item -LiteralPath $workspaceDest -Destination $workspaceBackup -Force }

$runnerText = @'
$ErrorActionPreference = 'Stop'
$root = 'D:\Sonic\companion'
$encrypted = Get-Content -LiteralPath (Join-Path $root 'device-token.dpapi') -Raw
$secure = ConvertTo-SecureString $encrypted
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:SONIC_DEVICE_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:SONIC_BASE_URL = 'https://sonic-web-staging.up.railway.app'
    $env:SONIC_DEVICE_ID = 'TRADEVICEPC'
    $env:SONIC_WORKSPACE_ROOT = 'D:\Sonic\work'
    $env:SONIC_ENABLE_POWERSHELL_EXEC = '__SONIC_PS_ENABLE__'
    & 'D:\Sonic\.venv\Scripts\python.exe' -u (Join-Path $root 'windows_agent_v05.py')
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $secure.Dispose()
    foreach ($key in @('SONIC_DEVICE_TOKEN','SONIC_BASE_URL','SONIC_DEVICE_ID',
                       'SONIC_WORKSPACE_ROOT','SONIC_ENABLE_POWERSHELL_EXEC')) {
        Remove-Item -Path ('Env:' + $key) -ErrorAction SilentlyContinue
    }
}
'@
$runnerText = $runnerText.Replace('__SONIC_PS_ENABLE__', $enableValue)
$previousActions = $task.Actions
try {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction Stop
    Copy-Item -LiteralPath (Join-Path $stage 'windows_agent_v05.py') -Destination $destination -Force
    Copy-Item -LiteralPath (Join-Path $stage 'windows_command_v08.py') -Destination $brokerDest -Force
    Copy-Item -LiteralPath (Join-Path $stage 'windows_workspace_v082.py') -Destination $workspaceDest -Force
    $runnerText | Set-Content -LiteralPath $runner -Encoding UTF8
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        '-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "' + $runner + '"')
    Set-ScheduledTask -TaskName $taskName -Action $action -ErrorAction Stop | Out-Null
    Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
    Write-Host 'SONIC V0.8 installed as Limited user Scheduled Task.'
    Write-Host 'No ports opened. Verify heartbeat and capability list in SONIC Devices.'
} catch {
    Write-Warning 'Install failed. Restoring the previous SONIC Scheduled Task.'
    if(Test-Path $backup) { Copy-Item -LiteralPath $backup -Destination $destination -Force }
    if(Test-Path $brokerBackup) { Copy-Item -LiteralPath $brokerBackup -Destination $brokerDest -Force }
    if(Test-Path $workspaceBackup) { Copy-Item -LiteralPath $workspaceBackup -Destination $workspaceDest -Force }
    Set-ScheduledTask -TaskName $taskName -Action $previousActions | Out-Null
    Start-ScheduledTask -TaskName $taskName
    throw
}
