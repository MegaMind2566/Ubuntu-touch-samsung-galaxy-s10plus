@echo off
setlocal
echo Samsung S10+ - test 2 con diagnostica integrata nel kernel
echo Scrive solo BOOT dal test 1 verificato. Lascia TWRP aperta e USB collegato.
echo Il test salva piccoli log nella memoria dati. Non avvia Ubuntu.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-diagnostic-2.ps1" -PackageRoot "%~dp0." -Mode Apply
set "UT_EARLY_DIAG_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_EARLY_DIAG_EXIT%
