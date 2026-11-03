@echo off
setlocal
cd /d "%~dp0"
title Valtix GUI Edition - Install

echo.
echo   VALTIX - GUI EDITION - INSTALLER
echo   =================================
echo   Native desktop app. No web server, no browser.
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo   [!] Python was not found on PATH.
    echo       Install Python 3.12+ from https://www.python.org/downloads/
    echo       and make sure "Add python.exe to PATH" is checked.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   [1/3] Using Python %PYVER%

python -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo   [!] tkinter is missing - reinstall Python and enable tcl/tk.
    pause
    exit /b 1
)
echo         tkinter OK

echo   [2/3] Installing pinned packages...
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo   [!] Package install failed. Check your internet connection and retry.
    pause
    exit /b 1
)

echo   [3/3] Verifying install...
python -c "import requests, tzdata, PIL" >nul 2>nul
if errorlevel 1 (
    echo   [!] Verification failed.
    pause
    exit /b 1
)

echo.
echo   Done. Start Valtix with start.bat (or: python run.py)
echo.

set /p LAUNCH="Launch Valtix now? [y/N] "
if /i "%LAUNCH%"=="y" start "" pythonw run.py
endlocal
