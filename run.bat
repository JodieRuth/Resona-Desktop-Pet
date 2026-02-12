@echo off
setlocal
cd /d %~dp0

:: 0. Check C++ Redistributable
powershell -Command "if (!(Test-Path 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64') -and !(Test-Path 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64')) { exit 1 } else { exit 0 }" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Microsoft Visual C++ Redistributable (2015-2022) is NOT installed!
    echo This is required for the application to run.
    echo Please download and install it from: https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo.
    pause
    exit /b
)

:: 1. Check local runtime
if exist "runtime\python.exe" (
    set "PYTHON_EXEC=runtime\python.exe"
    goto START
)

:: 2. Check virtual environment
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXEC=venv\Scripts\python.exe"
    goto START
)

:: 3. Check system python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXEC=python"
    goto START
)

echo [ERROR] No valid Python environment found! Please run setup.ps1 first.
pause
exit /b

:START
echo [Resona] Using environment: %PYTHON_EXEC%
%PYTHON_EXEC% main.py
if %errorlevel% neq 0 (
    echo [Resona] Program exited with error code: %errorlevel%
    pause
)
endlocal
