@echo off
setlocal
echo Samsung S10+ - controllo della recovery prima di Ubuntu Touch
echo Lettura tramite USB. Nessuna installazione o cancellazione.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check-recovery.ps1" -PackageRoot "%~dp0."
set "RECOVERY_CHECK_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %RECOVERY_CHECK_EXIT%
