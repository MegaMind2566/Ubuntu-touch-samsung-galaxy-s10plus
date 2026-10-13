@echo off
setlocal
echo Primo avvio Ubuntu Touch sul Samsung S10+ SM-G975F - installazione tramite TWRP
echo Scrive SYSTEM e BOOT e verifica le immagini dopo la scrittura.
echo Lascia il telefono nella schermata principale TWRP e collegato via USB.
echo Usa i file gia preparati e il reset dati gia verificato. Non esegue Format Data.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-ubuntu-twrp.ps1" -PackageRoot "%~dp0."
set "UT_TWRP_INSTALL_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_TWRP_INSTALL_EXIT%
