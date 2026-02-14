@echo off
setlocal enabledelayedexpansion
title Resona Tools Launcher
cd /d %~dp0

:: 1. Check local runtime
if exist "runtime\python.exe" (
    set "PYTHON_EXEC=runtime\python.exe"
    goto FIND_TOOLS
)

:: 2. Check virtual environment
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXEC=venv\Scripts\python.exe"
    goto FIND_TOOLS
)

:: 3. Check .venv virtual environment
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXEC=.venv\Scripts\python.exe"
    goto FIND_TOOLS
)

:: 4. Check system python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXEC=python"
    goto FIND_TOOLS
)

echo [ERROR] No valid Python environment found! 
echo Please ensure 'runtime' or 'venv' exists, or Python is in your PATH.
echo.
pause
exit /b

:FIND_TOOLS
echo Using environment: %PYTHON_EXEC%
echo.
echo Available tools in tools/:
echo --------------------------------

set "count=0"
for %%f in (tools\*.py) do (
    set /a count+=1
    set "tool_!count!=%%f"
    echo !count!. %%~nxf
)

if %count% equ 0 (
    echo [ERROR] No Python scripts found in tools/ folder.
    pause
    exit /b
)

echo --------------------------------
echo.
set /p choice="Enter the number to run (or press Enter to exit): "

if "%choice%"=="" exit /b

if defined tool_%choice% (
    set "selected_tool=!tool_%choice%!"
    echo.
    echo [Resona] Launching: !selected_tool!
    echo --------------------------------
    "%PYTHON_EXEC%" "!selected_tool!"
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] Tool exited with error code: !errorlevel!
        pause
    ) else (
        echo.
        echo [Resona] Tool finished successfully.
        pause
    )
) else (
    echo [ERROR] Invalid selection: %choice%
    pause
)

endlocal
