@echo off
setlocal
echo Primo test della recovery sul Samsung S10+ SM-G975F - versione 2
echo Questo programma scrive le partizioni VBMETA e RECOVERY.
echo Il telefono deve essere sbloccato, in Download Mode e collegato via USB.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\flash-recovery-test.ps1" -PackageRoot "%~dp0."
set "RECOVERY_TEST_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %RECOVERY_TEST_EXIT%
