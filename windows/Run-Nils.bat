@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Virtual environment not found. Run Install-Nils-Windows.bat first.
  pause
  exit /b 1
)
start "" wscript.exe "%~dp0Run-Nils.vbs"
