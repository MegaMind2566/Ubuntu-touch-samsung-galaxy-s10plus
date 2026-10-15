@echo off
setlocal
echo Samsung S10+ - lettura dei log grafici Ubuntu BOOT 6
echo Lascia la schermata principale TWRP aperta e USB collegato.
echo Nessuna scrittura, cancellazione, mount o riavvio.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Estrai tutto questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\collect-ubuntu-graphics.py" --root "%~dp0."
set "UT_GRAPHICS6_READ_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_GRAPHICS6_READ_EXIT%
