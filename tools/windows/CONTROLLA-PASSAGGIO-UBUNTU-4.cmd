@echo off
setlocal
echo Samsung S10+ - controllo del passaggio a Ubuntu dopo BOOT 4
echo Lascia la schermata principale TWRP aperta e USB collegato.
echo Legge log e file di avvio. SYSTEM viene montata temporaneamente in sola lettura.
echo Nessun flash, riparazione, cancellazione o riavvio.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia il contenuto dello ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\collect-ubuntu-userspace.py" --root "%~dp0."
set "UT_USERSPACE4_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_USERSPACE4_EXIT%
