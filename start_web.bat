@echo off
chcp 65001 >nul
title 2GIS Lead Generator - Веб-интерфейс

cd /d "%~dp0"
call venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt -q
)

echo.
echo Приложение запущено. Браузер откроется автоматически.
echo НЕ ЗАКРЫВАЙТЕ это окно. Для остановки: Ctrl+C
echo.
python web_app.py
pause
