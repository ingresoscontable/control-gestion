@echo off
chcp 65001 >nul
echo ==============================================
echo   Quitando el arranque automatico
echo ==============================================
echo.

set "DESTINO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ControlGestion.vbs"

if exist "%DESTINO%" (
  del "%DESTINO%"
  echo Listo. El servidor ya no arranca solo al iniciar sesion.
  echo El que este corriendo ahora sigue corriendo: usa detener.bat.
) else (
  echo El arranque automatico no estaba instalado.
)
echo.
pause
