@echo off
setlocal
echo Samsung S10+ - ripristino del BOOT Ubuntu 4
echo Scrive solo BOOT da Ubuntu BOOT 6 verificato. TWRP aperta e USB collegato.
echo Ripristina il BOOT Ubuntu 4 precedente. Non ripristina Android o un Ubuntu funzionante.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update-6.ps1" -PackageRoot "%~dp0." -Mode Restore
set "UT_BOOT6_RESTORE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT6_RESTORE_EXIT%
