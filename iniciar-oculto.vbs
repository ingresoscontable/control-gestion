' Control de Gestion - arranque en segundo plano (sin ventana).
' Doble clic aqui y el servidor queda corriendo de fondo, sin ventana negra.
' Para detenerlo: doble clic en detener.bat.

Option Explicit

Dim sh, ruta, exe, py
Set sh = CreateObject("WScript.Shell")
ruta = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.CurrentDirectory = ruta

exe = ruta & ".venv\Scripts\python.exe"
py = ruta & "main.py"

If Not sh.FileExists(exe) Then
  MsgBox "Todavia no esta instalado." & vbCrLf & vbCrLf & _
         "Ejecuta primero instalar.bat.", _
         vbExclamation, "Control de Gestion"
  WScript.Quit 1
End If

' Lanza python con la ventana oculta (estilo 0) y no espera a que termine.
sh.Run """" & exe & """ """ & py & """", 0, False

WScript.Sleep 1200
MsgBox "Servidor iniciado en segundo plano (sin ventana visible)." & vbCrLf & vbCrLf & _
       "En esta PC:   http://localhost:8000" & vbCrLf & _
       "Otras PC:     http://<IP de esta PC>:8000" & vbCrLf & vbCrLf & _
       "Para detenerlo: doble clic en detener.bat", _
       vbInformation, "Control de Gestion"
