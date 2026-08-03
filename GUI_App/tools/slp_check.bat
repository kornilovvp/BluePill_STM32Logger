@echo off
rem SLP v1 link check runner. Usage: slp_check.bat [COMx] [seconds]
rem Defaults: COM11, 10 seconds. Requires: pip install pyserial
setlocal

chcp 65001 >nul

set "PORT=%~1"
if "%PORT%"=="" set "PORT=COM11"

set "SECS=%~2"
if "%SECS%"=="" set "SECS=10"

echo === SLP check: %PORT%, %SECS% s ===
python "%~dp0slp_check.py" %PORT% %SECS%

echo.
pause
