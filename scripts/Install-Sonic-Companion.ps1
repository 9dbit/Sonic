# SONIC V0.9.0 Limited-user companion upgrade.
# Local owner-initiated opt-in only, outbound HTTPS, no administrator elevation.
# Graceful WM_CLOSE can interrupt local EAs in MetaTrader 5.
param(
    [switch]$Install,
    [switch]$EnablePowerShell,
    [switch]$EnableWindowControl,
    [string]$MT5Executable = ''
)
$ErrorActionPreference = 'Stop'
$root = 'D:\Sonic\companion'
$workspace = 'D:\Sonic\work'
$python = 'D:\Sonic\.venv\Scripts\python.exe'
$tokenFile = Join-Path $root 'device-token.dpapi'
$agentSource = Join-Path $PSScriptRoot 'windows_agent_v05.py'
$brokerSource = Join-Path $PSScriptRoot 'windows_command_v08.py'
$workspaceSource = Join-Path $PSScriptRoot 'windows_workspace_v082.py'
$windowSource = Join-Path $PSScriptRoot 'windows_window_v090.py'
$taskName = 'SONIC Read-only Companion'

foreach ($path in @($root,$workspace,$python,$tokenFile,$agentSource,$brokerSource,$workspaceSource,$windowSource)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing requirement: $path" }
}
& $python -c 'import psutil' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'SONIC needs psutil in D:\Sonic\.venv' }
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
if ($task.Principal.RunLevel -eq 'Highest') {
    throw 'Refusing elevated task. SONIC must run with Limited privileges.'
}
$enableValue = if ($EnablePowerShell) { '1' } else { '0' }
$windowValue = if ($EnableWindowControl) { '1' } else { '0' }
if ($MT5Executable -and -not $EnableWindowControl) {
    throw 'MT5Executable requires explicit -EnableWindowControl.'
}
if ($MT5Executable) {
    if ($MT5Executable -match '[\r\n\x00]' -or
        $MT5Executable.StartsWith('\\') -or
        $MT5Executable -notmatch '[\\/]terminal(?:64)?[.]exe$') {
        throw 'MT5Executable must be an absolute local terminal64.exe or terminal.exe path.'
    }
    if (-not [IO.Path]::IsPathRooted($MT5Executable) -or
        -not (Test-Path -LiteralPath $MT5Executable -PathType Leaf)) {
        throw 'MT5 executable must exist at the explicitly configured local path.'
    }
}
$escapedMT5 = $MT5Executable.Replace("'", "''")
Write-Host 'SONIC V0.9.0 companion / Limited user / outbound HTTPS.'
Write-Host ('Window Control opt-in: ' + [bool]$EnableWindowControl)
Write-Host ('PowerShell opt-in: ' + [bool]$EnablePowerShell)
Write-Host 'Window closing uses WM_CLOSE only. MetaTrader 5 EAs may stop, positions remain at broker.'
Write-Host 'Every opening or closing action still requires explicit owner approval in SONIC.'
if (-not $Install) {
    Write-Host 'Dry run only: no Scheduled Task or installed companion files were changed.'
    Write-Host 'Use -Install -EnableWindowControl only after reviewing and accepting local GUI risks.'
    return
}

$stage = Join-Path $workspace 'sonic-v090-install-candidate'
New-Item -ItemType Directory -Force -Path $stage | Out-Null
foreach ($source in @($agentSource,$brokerSource,$workspaceSource,$windowSource)) {
    Copy-Item -LiteralPath $source -Destination (Join-Path $stage (Split-Path $source -Leaf)) -Force
}

# Preflight authenticates the companion and advertises capabilities, but never
# dequeues a PC command. Old Scheduled Task and files remain untouched here.
$encrypted = Get-Content -LiteralPath $tokenFile -Raw
$secure = ConvertTo-SecureString $encrypted
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:SONIC_DEVICE_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:SONIC_BASE_URL = 'https://sonic-web-staging.up.railway.app'
    $env:SONIC_DEVICE_ID = 'TRADEVICEPC'
    $env:SONIC_WORKSPACE_ROOT = $workspace
    $env:SONIC_ENABLE_POWERSHELL_EXEC = $enableValue
    $env:SONIC_WINDOW_CONTROL_ENABLED = $windowValue
    $env:SONIC_MT5_EXE_PATH = $MT5Executable
    & $python -u (Join-Path $stage 'windows_agent_v05.py') --preflight
    if ($LASTEXITCODE -ne 0) {
        throw 'SONIC V0.9 preflight failed; existing Scheduled Task remains unchanged.'
    }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $secure.Dispose()
    foreach ($key in @('SONIC_DEVICE_TOKEN','SONIC_BASE_URL','SONIC_DEVICE_ID',
                       'SONIC_WORKSPACE_ROOT','SONIC_ENABLE_POWERSHELL_EXEC',
                       'SONIC_WINDOW_CONTROL_ENABLED','SONIC_MT5_EXE_PATH')) {
        Remove-Item -Path ('Env:' + $key) -ErrorAction SilentlyContinue
    }
}

$destinations = @(
    @{ Source='windows_agent_v05.py';       Installed=(Join-Path $root 'windows_agent_v05.py') },
    @{ Source='windows_command_v08.py';     Installed=(Join-Path $root 'windows_command_v08.py') },
    @{ Source='windows_workspace_v082.py';  Installed=(Join-Path $root 'windows_workspace_v082.py') },
    @{ Source='windows_window_v090.py';     Installed=(Join-Path $root 'windows_window_v090.py') }
)
$runner = Join-Path $root 'Start-SONIC-Companion-V08.ps1'
$backups = @()
foreach ($file in $destinations) {
    $prior = Test-Path -LiteralPath $file.Installed
    $backup = $file.Installed + '.before-v090.bak'
    if ($prior) {
        Copy-Item -LiteralPath $file.Installed -Destination $backup -Force
    }
    $backups += @{ Installed=$file.Installed; Backup=$backup; Prior=$prior }
}
$oldRunnerPresent = Test-Path -LiteralPath $runner
$runnerBackup = $runner + '.before-v090.bak'
if ($oldRunnerPresent) { Copy-Item -LiteralPath $runner -Destination $runnerBackup -Force }

# Single-quoted here-string prevents interpolation of device credentials.
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
    $env:SONIC_WINDOW_CONTROL_ENABLED = '__SONIC_WINDOW_ENABLE__'
    $env:SONIC_MT5_EXE_PATH = '__SONIC_MT5_PATH__'
    & 'D:\Sonic\.venv\Scripts\python.exe' -u (Join-Path $root 'windows_agent_v05.py')
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $secure.Dispose()
    foreach ($key in @('SONIC_DEVICE_TOKEN','SONIC_BASE_URL','SONIC_DEVICE_ID',
                       'SONIC_WORKSPACE_ROOT','SONIC_ENABLE_POWERSHELL_EXEC',
                       'SONIC_WINDOW_CONTROL_ENABLED','SONIC_MT5_EXE_PATH')) {
        Remove-Item -Path ('Env:' + $key) -ErrorAction SilentlyContinue
    }
}
'@
$runnerText = $runnerText.Replace('__SONIC_PS_ENABLE__', $enableValue)
$runnerText = $runnerText.Replace('__SONIC_WINDOW_ENABLE__', $windowValue)
$runnerText = $runnerText.Replace('__SONIC_MT5_PATH__', $escapedMT5)
$previousActions = $task.Actions

try {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction Stop
    foreach ($file in $destinations) {
        Copy-Item -LiteralPath (Join-Path $stage $file.Source) -Destination $file.Installed -Force
    }
    $runnerText | Set-Content -LiteralPath $runner -Encoding UTF8
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        '-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "' + $runner + '"')
    Set-ScheduledTask -TaskName $taskName -Action $action -ErrorAction Stop | Out-Null
    Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
    Write-Host 'SONIC V0.9.0 installed as an outbound-only, Limited-user Scheduled Task.'
    Write-Host 'Check Devices for a fresh agent 0.9.0 heartbeat before using Window Control.'
} catch {
    Write-Warning 'Upgrade failed. Restoring previous companion, runner and Scheduled Task action.'
    foreach ($old in $backups) {
        if ($old.Prior -and (Test-Path -LiteralPath $old.Backup)) {
            Copy-Item -LiteralPath $old.Backup -Destination $old.Installed -Force
        } elseif (-not $old.Prior) {
            Remove-Item -LiteralPath $old.Installed -Force -ErrorAction SilentlyContinue
        }
    }
    if ($oldRunnerPresent -and (Test-Path -LiteralPath $runnerBackup)) {
        Copy-Item -LiteralPath $runnerBackup -Destination $runner -Force
    } elseif (-not $oldRunnerPresent) {
        Remove-Item -LiteralPath $runner -Force -ErrorAction SilentlyContinue
    }
    Set-ScheduledTask -TaskName $taskName -Action $previousActions -ErrorAction Stop | Out-Null
    Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
    throw
}
