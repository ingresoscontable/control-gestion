@echo off
chcp 65001 >nul

net session >nul 2>&1
if errorlevel 1 (
  echo Este archivo debe ejecutarse como Administrador.
  echo Haz clic derecho sobre el archivo y elige "Ejecutar como administrador".
  pause
  exit /b 1
)

set PUERTO=8000
if not "%CG_PORT%"=="" set PUERTO=%CG_PORT%

netsh advfirewall firewall delete rule name="Control de Gestion" >nul 2>&1
netsh advfirewall firewall add rule name="Control de Gestion" dir=in action=allow protocol=TCP localport=%PUERTO%

echo.
echo Listo. El puerto %PUERTO% queda abierto en la red local.
pause
