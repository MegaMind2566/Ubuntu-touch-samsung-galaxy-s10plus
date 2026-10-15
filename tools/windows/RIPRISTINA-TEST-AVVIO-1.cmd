@echo off
setlocal
echo Samsung S10+ - ripristino del BOOT del test 1
echo Scrive solo BOOT dal test 2 verificato. TWRP aperta e USB collegato.
echo Ripristina il test precedente. Non ripristina Android o un Ubuntu funzionante.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-diagnostic-2.ps1" -PackageRoot "%~dp0." -Mode Restore
set "UT_EARLY_DIAG_RESTORE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_EARLY_DIAG_RESTORE_EXIT%
