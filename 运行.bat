@echo off
REM Windows one-click launcher for the six-city temperature crawler.
REM This file is intentionally ASCII-only: cmd.exe decodes a batch file with
REM the console code page in effect when the file is opened, so Chinese text
REM here would be garbled on some systems. All Chinese output comes from the
REM Python program, which writes to the console through the Unicode API.
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" goto use_venv
python --version >nul 2>nul
if %errorlevel%==0 goto use_python
echo.
echo [ERROR] Python was not found.
echo Install Python 3.11 or newer, then run this file again.
echo Details: README.md and the Chinese quick-start file in this folder.
echo.
pause
exit /b

:use_venv
"%~dp0.venv\Scripts\python.exe" -m sixcity_temp %*
goto end

:use_python
set "PYTHONPATH=%~dp0src"
python -m sixcity_temp %*

:end
echo.
echo ============================================
echo Done. Excel files are written to the output directory.
echo If the log above shows a fetch failure, check the network and run again.
echo ============================================
pause
