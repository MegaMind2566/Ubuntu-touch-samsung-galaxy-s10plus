@echo off
setlocal
echo Samsung S10+ - ripristino del BOOT 2 precedente al test
echo Aggiorna solo BOOT dal test diagnostico verificato. TWRP aperta e USB collegato.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-diagnostic-1.ps1" -PackageRoot "%~dp0." -Mode Restore
set "UT_BOOT_DIAG_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT_DIAG_EXIT%
