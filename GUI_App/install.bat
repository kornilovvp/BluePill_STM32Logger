@echo off
rem Install GUI_App dependencies (list: requirements.txt).
rem Details are printed by tools\install.py (in Russian, UTF-8).
rem NOTE: keep this file ASCII-only - cmd.exe breaks on UTF-8 text.
chcp 65001 >nul
python "%~dp0tools\install.py"
echo.
pause
