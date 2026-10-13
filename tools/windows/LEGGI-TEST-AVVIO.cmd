@echo off
setlocal
echo Samsung S10+ - lettura del risultato del test
echo Torna prima nella schermata principale TWRP. Lascia USB collegato.
echo Lettura dei log. Nessuna scrittura, cancellazione, mount o riavvio.
echo.
if not exist "%~dp0tools\python\python.exe" (
    echo Copia tutti i file di questo ZIP nella cartella originale di installazione Ubuntu.
    pause
    exit /b 2
)
"%~dp0tools\python\python.exe" -I "%~dp0scripts\collect-boot-diagnostic.py" --root "%~dp0."
set "UT_BOOT_DIAG_READ_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT_DIAG_READ_EXIT%
