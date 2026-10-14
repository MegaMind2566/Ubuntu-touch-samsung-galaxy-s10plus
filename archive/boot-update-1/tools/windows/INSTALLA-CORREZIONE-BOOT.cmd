@echo off
setlocal
echo Samsung S10+ - correzione del caricamento del ramdisk
echo Questo programma aggiorna solo BOOT. Lascia il telefono in TWRP e USB collegato.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update.ps1" -PackageRoot "%~dp0." -Mode Apply
set "UT_BOOT_UPDATE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT_UPDATE_EXIT%
