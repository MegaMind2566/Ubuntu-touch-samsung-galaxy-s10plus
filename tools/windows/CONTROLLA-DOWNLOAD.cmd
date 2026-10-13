@echo off
setlocal
cd /d "%~dp0"
echo Controllo del Samsung S10+ in Download Mode
echo Lettura delle partizioni. Nessuna installazione o cancellazione.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check-download-mode.ps1"
set "CHECK_RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %CHECK_RESULT%
