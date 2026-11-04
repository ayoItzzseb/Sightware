@echo off
setlocal
cd /d "%~dp0"
title Sightware GUI Edition - Build .exe

echo.
echo   SIGHTWARE - GUI EDITION - EXE BUILDER
echo   ==================================
echo   Builds a single dist\Sightware.exe (PyInstaller, onefile, windowed).
echo   Build-time only: PyInstaller is installed into your Python.
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo   [!] Python not found on PATH.
    pause
    exit /b 1
)

echo   [1/2] Installing PyInstaller (build-time only)...
python -m pip install --quiet pyinstaller
if errorlevel 1 (
    echo   [!] Could not install PyInstaller.
    pause
    exit /b 1
)

echo   [2/2] Building...
python -m PyInstaller Sightware.spec --noconfirm --clean
if errorlevel 1 (
    echo   [!] Build failed - see the output above.
    pause
    exit /b 1
)

echo.
echo   Done: dist\Sightware.exe
echo   Copy it anywhere - it creates data\ and logs\ folders next to itself.
echo.
pause
endlocal
