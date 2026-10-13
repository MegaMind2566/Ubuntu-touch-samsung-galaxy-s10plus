@echo off
setlocal
echo Samsung S10+ - ripristino del BOOT sperimentale precedente
echo Questo programma riscrive solo BOOT. Non ripristina Android completo.
echo Usalo dopo il controllo del rapporto della correzione, con TWRP e USB collegato.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update.ps1" -PackageRoot "%~dp0." -Mode Restore
set "UT_BOOT_RESTORE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT_RESTORE_EXIT%
