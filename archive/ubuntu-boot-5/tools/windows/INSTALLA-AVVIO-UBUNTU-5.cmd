@echo off
setlocal
echo Samsung S10+ - avvio Ubuntu con BOOT 5
echo Scrive solo BOOT da Ubuntu BOOT 4 verificato. TWRP aperta e USB collegato.
echo Avvia l initramfs Ubuntu e salva log di avanzamento nella memoria dati.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update-5.ps1" -PackageRoot "%~dp0." -Mode Apply
set "UT_BOOT5_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT5_EXIT%
