# SPDX-License-Identifier: Apache-2.0
# Maris3D one-line install for Windows (PowerShell):
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/slm4apps/maris3d/main/install.ps1 | iex"
#
# Same steps as install.sh: finds Python 3.9+, makes a private environment in
# %LOCALAPPDATA%\maris3d\venv, installs the maris3d package from the release, then runs
# `maris3d install` (the Blender add-on, the model files from Hugging Face, llama-server, the voice and picture
# modules, a self-test), then starts the local server.
$ErrorActionPreference = "Stop"

$Version = "0.3.0"
$WheelUrl = "https://github.com/slm4apps/maris3d/releases/download/v$Version/maris3d-$Version-py3-none-any.whl"
if ($env:MARIS3D_WHEEL) { $WheelUrl = $env:MARIS3D_WHEEL }   # a local wheel, for testing (as in install.sh)
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

# Keep the extra arguments a list: a lone string ("-3") splatted into a native command runs nothing.
$exe = $Py[0]; $pyargs = @($Py | Select-Object -Skip 1)
Say "making a private environment in $HomeDir\venv"
& $exe @pyargs -m venv (Join-Path $HomeDir "venv")
$VPy = Join-Path $HomeDir "venv\Scripts\python.exe"
if (-not (Test-Path $VPy)) { throw "maris3d: could not make the environment in $HomeDir\venv with $($Py -join ' ')" }
& $VPy -m pip install --quiet --upgrade pip | Out-Null

Say "installing maris3d $Version"
& $VPy -m pip install --quiet --upgrade $WheelUrl
if ($LASTEXITCODE -ne 0) { throw "maris3d: could not install from $WheelUrl" }

# The command goes on PATH as a small .cmd that runs the signed python.exe: Windows 11 Smart App Control
# blocks the unsigned launcher .exe that pip makes (venv\Scripts\maris3d.exe).
$Bin = Join-Path $HomeDir "bin"
New-Item -ItemType Directory -Force $Bin | Out-Null
Set-Content -Path (Join-Path $Bin "maris3d.cmd") -Encoding ASCII -Value "@`"$VPy`" -m maris3d %*"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($env:MARIS3D_NO_MODIFY_PATH) {
    Say "left your PATH alone (MARIS3D_NO_MODIFY_PATH is set); run $Bin\maris3d.cmd"
} elseif (-not ($UserPath -split ";" | Where-Object { $_ -eq $Bin })) {
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$Bin", "User")
    Say "added $Bin to your PATH (new terminals will find 'maris3d')"
}

Say "setting up Blender and the model"
# No @args: under "irm | iex" there are none, and in nested PowerShell hosts $args can hold the caller's own values.
$ask = if ($env:MARIS3D_ASK) { @() } else { @("--express") }   # running this is the yes; MARIS3D_ASK=1 asks first
& $VPy -m maris3d install @ask
if ($LASTEXITCODE -ne 0) { throw "maris3d: setup did not finish; run 'maris3d doctor' in a new terminal to see what is missing" }

# start the local server so it is ready when Blender opens (it keeps running in the background)
& $VPy -m maris3d serve start
if ($LASTEXITCODE -eq 0) { Say "done. Open Blender, press N in the 3D View and pick the Maris3D Copilot tab." }
else { Say "the server did not start; run 'maris3d doctor' in a new terminal to see what is missing." }
