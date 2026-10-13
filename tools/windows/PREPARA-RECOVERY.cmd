@echo off
setlocal
cd /d "%~dp0"
echo Preparazione del test recovery per Samsung S10+ SM-G975F/DS
echo Questa fase crea file sul PC. Non comunica con il telefono.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare-recovery.ps1" -PackageRoot "%~dp0." -StockFirmware "%~1"
set "PREPARE_RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %PREPARE_RESULT%
