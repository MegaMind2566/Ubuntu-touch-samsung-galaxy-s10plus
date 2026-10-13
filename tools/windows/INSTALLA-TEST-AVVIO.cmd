@echo off
setlocal
echo Samsung S10+ - test temporaneo di kernel e ramdisk
echo Aggiorna solo BOOT dalla versione 2 verificata. TWRP aperta e USB collegato.
echo Il test salva piccoli log nella memoria dati. Non avvia Ubuntu.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-diagnostic-1.ps1" -PackageRoot "%~dp0." -Mode Apply
set "UT_BOOT_DIAG_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT_DIAG_EXIT%
