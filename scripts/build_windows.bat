@echo off
title ZenFlux Agent - Windows Build

echo.
echo ============================================================
echo   ZenFlux Agent - Windows One-Click Build
echo ============================================================
echo.
echo   This script will:
echo     1. Check and install Python 3.12, Node.js, Rust if missing
echo     2. Build Python backend with PyInstaller
echo     3. Build desktop app as NSIS installer
echo.
echo   No manual steps needed. Please wait...
echo   First run: ~15-30 min, subsequent: ~5-10 min
echo.
echo ============================================================
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0scripts\build_app_windows.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [FAILED] Build error. Check logs above.
    echo.
    pause
    exit /b 1
)

echo.
echo [DONE] Installer generated in dist\ folder!
echo.
pause
