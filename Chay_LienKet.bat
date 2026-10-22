@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "Lấy nội lực\.venv\Scripts\pythonw.exe" (
  start "" "Lấy nội lực\.venv\Scripts\pythonw.exe" run.py %*
) else (
  start "" pythonw run.py %*
)
