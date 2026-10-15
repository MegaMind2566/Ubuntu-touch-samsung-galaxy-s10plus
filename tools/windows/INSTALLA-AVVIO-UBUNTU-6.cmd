@echo off
setlocal
echo Samsung S10+ - avvio Ubuntu con BOOT 6
echo Scrive solo BOOT da Ubuntu BOOT 5 verificato. TWRP aperta e USB collegato.
echo Corregge il panic USB e applica i profili del dispositivo in RAM.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-boot-update-6.ps1" -PackageRoot "%~dp0." -Mode Apply
set "UT_BOOT6_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT6_EXIT%
