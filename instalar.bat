@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==============================================
echo   Instalando Control de Gestion
echo ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python en esta PC.
  echo Descargalo de https://www.python.org/downloads/windows/
  echo IMPORTANTE: al instalar, marca la casilla "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  python -m venv .venv
  if errorlevel 1 (
    echo No se pudo crear el entorno virtual.
    pause
    exit /b 1
  )
)

echo Instalando dependencias...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Listo. Para arrancar el sistema ejecuta: iniciar.bat
pause
