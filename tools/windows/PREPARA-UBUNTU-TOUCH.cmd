@echo off
setlocal
echo Ubuntu Touch 24.04 - preparazione locale per il Samsung S10+
echo Questa fase prepara i file sul PC. Non modifica il telefono.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare-ubuntu-install.ps1" -PackageRoot "%~dp0." %*
set "UT_PREPARATION_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_PREPARATION_EXIT%
