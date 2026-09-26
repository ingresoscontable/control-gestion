@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==============================================
echo   Arranque automatico de Control de Gestion
echo ==============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Todavia no esta instalado.
  echo Ejecuta primero instalar.bat
  pause
  exit /b 1
)

set "DESTINO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ControlGestion.vbs"
set "RUTA=%~dp0"
if "%RUTA:~-1%"=="\" set "RUTA=%RUTA:~0,-1%"

echo Carpeta de inicio de Windows:
echo   %DESTINO%
echo.

> "%DESTINO%" echo Option Explicit
>>"%DESTINO%" echo CreateObject^("WScript.Shell"^).Run "wscript.exe ""%RUTA%\iniciar-oculto.vbs"" /silencioso", 0, False

echo.
if exist "%DESTINO%" (
  echo Listo. Cada vez que inicies sesion en Windows, el servidor arranca
  echo solo y en segundo plano, sin ninguna ventana.
  echo.
  echo Para quitarlo: doble clic en desinstalar-arranque.bat
  echo Para detener el servidor que ya esta corriendo: detener.bat
) else (
  echo No se pudo crear el archivo. Revisa los permisos de la carpeta de inicio.
)
echo.
pause
