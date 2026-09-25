@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Todavia no esta instalado.
  echo Ejecuta primero instalar.bat
  pause
  exit /b 1
)

call ".venv\Scripts\python.exe" main.py
pause
