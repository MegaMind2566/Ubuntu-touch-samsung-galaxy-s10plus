@echo off
setlocal
echo Samsung S10+ BOOT 6 - annulla la correzione grafica
echo Lascia TWRP aperta e USB collegato.
echo Modifica solo i file della correzione nella memoria dati.
echo Nessuna immagine BOOT, SYSTEM o VENDOR viene riscritta.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Estrai tutto questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\manage-graphics-permissions.py" --root "%~dp0." --operation remove
set "UT_GRAPHICS_PERMISSIONS_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_GRAPHICS_PERMISSIONS_EXIT%
