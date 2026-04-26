$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function New-DesktopShortcut {
    param(
        [string]$TargetPath,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$ShortcutPath,
        [string]$IconLocation
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    if ($Arguments) {
        $shortcut.Arguments = $Arguments
    }
    $shortcut.WorkingDirectory = $WorkingDirectory
    if ($IconLocation) {
        $shortcut.IconLocation = $IconLocation
    }
    $shortcut.Save()
}

function Get-PythonExecutable {
    $candidates = @()

    try {
        $py312 = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $py312) {
            $candidates += $py312.Trim()
        }
    } catch {}

    try {
        $py = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $py) {
            $candidates += $py.Trim()
        }
    } catch {}

    $common = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    )
    $candidates += $common

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Ensure-Python {
    $python = Get-PythonExecutable
    if ($python) {
        return $python
    }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python 3.12 was not found and winget is unavailable. Install Python 3.12 first, then rerun this installer."
    }

    Write-Step "Installing Python 3.12 with winget"
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements

    $python = Get-PythonExecutable
    if (-not $python) {
        throw "Python installation completed, but python.exe was not found. Reopen this folder and run Install-Nils-Windows.bat again."
    }
    return $python
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Step "Checking Python"
$PythonExe = Ensure-Python
Write-Host "Using Python: $PythonExe"

$VenvDir = Join-Path $Root ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Step "Creating virtual environment"
    & $PythonExe -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment is missing python.exe"
}

Write-Step "Upgrading packaging tools"
& $VenvPython -m pip install --upgrade "pip<26" "setuptools<82" wheel

Write-Step "Installing PyTorch with CUDA support"
& $VenvPython -m pip install --index-url https://download.pytorch.org/whl/cu128 torch torchvision torchaudio

Write-Step "Installing Nils dependencies"
& $VenvPython -m pip install pygame-ce pillow requests qwen-tts soundfile faster-whisper imageio-ffmpeg

Write-Step "Validating runtime imports"
& $VenvPython -c "import torch, qwen_tts, pygame, soundfile, faster_whisper; print('Runtime OK')"

Write-Step "Creating desktop shortcut"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Nils Companion.lnk"
$Launcher = Join-Path $Root "Run-Nils.vbs"
$Icon = Join-Path $Root "riko.png"
New-DesktopShortcut `
    -TargetPath "wscript.exe" `
    -Arguments "`"$Launcher`"" `
    -WorkingDirectory $Root `
    -ShortcutPath $ShortcutPath `
    -IconLocation $Icon

Write-Step "Done"
Write-Host "You can start Nils with the desktop shortcut or Run-Nils.vbs" -ForegroundColor Green
