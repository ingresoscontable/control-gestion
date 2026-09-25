@echo off
chcp 65001 >nul
echo ==============================================
echo   Deteniendo Control de Gestion
echo ==============================================
echo.

set PUERTO=8000
if not "%CG_PORT%"=="" set PUERTO=%CG_PORT%

set "DETENIDO="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":%PUERTO%"') do (
  taskkill /f /pid %%p >nul 2>&1
  if not errorlevel 1 set "DETENIDO=1"
)

echo.
if defined DETENIDO (
  echo Servidor detenido.
) else (
  echo No hay ningun servidor escuchando en el puerto %PUERTO%.
)
pause
