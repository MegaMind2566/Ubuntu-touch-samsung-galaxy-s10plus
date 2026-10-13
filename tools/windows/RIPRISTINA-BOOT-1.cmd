@echo off
setlocal
echo Samsung S10+ - ritorno al BOOT sperimentale versione 1
echo Scrive solo BOOT. Non ripristina Android completo.
echo Usalo dopo il controllo del rapporto, con TWRP aperta e USB collegato.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update-2.ps1" -PackageRoot "%~dp0." -Mode Restore
set "UT_BOOT_HANDOFF_RESTORE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT_HANDOFF_RESTORE_EXIT%
