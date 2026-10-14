@echo off
setlocal
echo Samsung S10+ - correzione del passaggio al ramdisk Ubuntu
echo Aggiorna solo BOOT dalla versione 1 verificata. Lascia TWRP aperta e USB collegato.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update-2.ps1" -PackageRoot "%~dp0." -Mode Apply
set "UT_BOOT_HANDOFF_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT_HANDOFF_EXIT%
