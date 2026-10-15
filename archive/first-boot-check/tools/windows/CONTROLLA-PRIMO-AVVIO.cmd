@echo off
setlocal
echo Ubuntu Touch sul Samsung S10+ - raccolta del primo avvio
echo Lascia il telefono nella schermata principale TWRP, collegato via USB.
echo Lettura di log e metadati. Nessuna scrittura, cancellazione o riavvio.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia tutti i file di questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\collect-first-boot.py" --root "%~dp0."
set "UT_FIRST_BOOT_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_FIRST_BOOT_EXIT%
