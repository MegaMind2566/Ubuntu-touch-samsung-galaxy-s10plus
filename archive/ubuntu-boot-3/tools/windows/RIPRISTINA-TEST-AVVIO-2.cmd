@echo off
setlocal
echo Samsung S10+ - ripristino del BOOT del test 2
echo Scrive solo BOOT da Ubuntu BOOT 3 verificato. TWRP aperta e USB collegato.
echo Ripristina il test precedente. Non ripristina Android o un Ubuntu funzionante.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update-3.ps1" -PackageRoot "%~dp0." -Mode Restore
set "UT_BOOT3_RESTORE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT3_RESTORE_EXIT%
