@echo off
setlocal
echo Samsung S10+ BOOT 6 - legge il risultato della correzione grafica
echo Lascia TWRP aperta e USB collegato.
echo Legge solo i log. Nessuna scrittura sul telefono.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Estrai tutto questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\manage-graphics-permissions.py" --root "%~dp0." --operation read
set "UT_GRAPHICS_PERMISSIONS_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_GRAPHICS_PERMISSIONS_EXIT%
