$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
python -m venv .build-venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment.' }
$buildPython = Join-Path $projectRoot '.build-venv\Scripts\python.exe'
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies.' }
& $buildPython scripts/build_native.py
if ($LASTEXITCODE -ne 0) { throw 'Native build failed.' }
