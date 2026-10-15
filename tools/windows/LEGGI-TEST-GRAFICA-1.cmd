@echo off
setlocal
echo Samsung S10+ BOOT 6 - lettura del test grafico
echo Lascia TWRP aperta e USB collegato.
echo Legge solo i log del test. Nessuna scrittura sul telefono.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Estrai tutto questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\manage-graphics-probe.py" --root "%~dp0." --operation read
set "UT_GRAPHICS_PROBE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_GRAPHICS_PROBE_EXIT%
