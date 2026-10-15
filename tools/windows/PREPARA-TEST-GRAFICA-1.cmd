@echo off
setlocal
echo Samsung S10+ BOOT 6 - prepara un solo test grafico
echo Lascia TWRP aperta e USB collegato.
echo Scrive solo i file del test nella memoria dati. Nessuna partizione viene riscritta.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Estrai tutto questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\manage-graphics-probe.py" --root "%~dp0." --operation prepare
set "UT_GRAPHICS_PROBE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_GRAPHICS_PROBE_EXIT%
