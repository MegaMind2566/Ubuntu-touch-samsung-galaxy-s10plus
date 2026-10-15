@echo off
setlocal
echo Samsung S10+ - preparazione OFFLINE delle immagini firmware alpha
echo Verifica BOOT ed estrae SYSTEM sul PC. Nessun accesso al telefono.
echo.
"%~dp0tools\python\python.exe" -I "%~dp0scripts\prepare-firmware-images.py" --root "%~dp0."
set "UT_FIRMWARE_PREPARE_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_FIRMWARE_PREPARE_EXIT%
