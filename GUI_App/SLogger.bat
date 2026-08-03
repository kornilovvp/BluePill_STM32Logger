@echo off
rem ============================================================
rem  SLogger - 4-channel logger (2 analog + 2 digital, 10 kHz)
rem  Double-click to run. Options: --sim (no hardware), --port COMx
rem  NOTE: keep this file ASCII-only - cmd.exe breaks on UTF-8 text.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

python -m logger_app %*

if errorlevel 1 (
  echo.
  echo App exited with error code %errorlevel%.
  echo If this is the first run - execute install.bat first.
  pause
)
