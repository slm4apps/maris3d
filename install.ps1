# SPDX-License-Identifier: Apache-2.0
# Maris3D one-line install for Windows (PowerShell):
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/slm4apps/maris3d/main/install.ps1 | iex"
#
# Same steps as install.sh: finds Python 3.9+, makes a private environment in
# %LOCALAPPDATA%\maris3d\venv, installs the maris3d package from the release, then runs
# `maris3d install` (the Blender add-on, the model files from Hugging Face, llama-server, a self-test).
$ErrorActionPreference = "Stop"

$Version = "0.1.2"
$WheelUrl = "https://github.com/slm4apps/maris3d/releases/download/v$Version/maris3d-$Version-py3-none-any.whl"
$HomeDir = if ($env:MARIS3D_HOME) { $env:MARIS3D_HOME } else { Join-Path $env:LOCALAPPDATA "maris3d" }

function Say($msg) { Write-Host "maris3d: $msg" }

$Py = $null
foreach ($cand in @("py -3", "python", "python3")) {
    $exe, $rest = $cand.Split(" ", 2)
    if (Get-Command $exe -ErrorAction SilentlyContinue) {
        $args0 = @(); if ($rest) { $args0 += $rest }
        & $exe @args0 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $Py = @($exe) + $args0; break }
    }
}
if (-not $Py) { throw "maris3d: Python 3.9 or newer is needed: https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH')" }

$exe, $pyargs = $Py
Say "making a private environment in $HomeDir\venv"
& $exe @pyargs -m venv (Join-Path $HomeDir "venv")
$VPy = Join-Path $HomeDir "venv\Scripts\python.exe"
& $VPy -m pip install --quiet --upgrade pip | Out-Null

Say "installing maris3d $Version"
& $VPy -m pip install --quiet --upgrade $WheelUrl
if ($LASTEXITCODE -ne 0) { throw "maris3d: could not install from $WheelUrl" }

$Scripts = Join-Path $HomeDir "venv\Scripts"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not ($UserPath -split ";" | Where-Object { $_ -eq $Scripts })) {
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$Scripts", "User")
    Say "added $Scripts to your PATH (new terminals will find 'maris3d')"
}

Say "setting up Blender and the model"
& (Join-Path $Scripts "maris3d.exe") install @args
