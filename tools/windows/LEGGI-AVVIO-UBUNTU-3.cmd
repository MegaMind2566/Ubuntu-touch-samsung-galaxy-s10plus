@echo off
setlocal
echo Samsung S10+ - lettura dei log Ubuntu BOOT 3
echo Torna prima nella schermata principale TWRP. Lascia USB collegato.
echo Lettura dei log. Nessuna scrittura, cancellazione, mount o riavvio.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\collect-ubuntu-handoff.py" --root "%~dp0."
set "UT_BOOT3_READ_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT3_READ_EXIT%
