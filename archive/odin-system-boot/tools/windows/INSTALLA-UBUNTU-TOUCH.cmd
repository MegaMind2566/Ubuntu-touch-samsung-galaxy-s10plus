@echo off
setlocal
echo Primo avvio sperimentale Ubuntu Touch 24.04 sul Samsung S10+ SM-G975F
echo Scrive SYSTEM e BOOT. Richiede Format Data in TWRP: cancella la memoria interna.
echo Completa prima PREPARA-UBUNTU-TOUCH.cmd. Lascia il telefono in TWRP e USB collegato.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-ubuntu-touch.ps1" -PackageRoot "%~dp0."
set "UT_INSTALL_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_INSTALL_EXIT%
