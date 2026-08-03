@echo off
rem Установка зависимостей GUI_App (список — requirements.txt).
rem Запуск двойным кликом; подробности печатает install.py.
chcp 65001 >nul
python "%~dp0install.py"
echo.
pause
