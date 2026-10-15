@echo off
setlocal
echo Samsung S10+ - avvio Ubuntu con BOOT 4
echo Scrive solo BOOT da Ubuntu BOOT 3 verificato. TWRP aperta e USB collegato.
echo Avvia l initramfs Ubuntu e salva log di avanzamento nella memoria dati.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update-4.ps1" -PackageRoot "%~dp0." -Mode Apply
set "UT_BOOT4_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT4_EXIT%
