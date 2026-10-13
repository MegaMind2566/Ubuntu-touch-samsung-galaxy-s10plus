@echo off
setlocal
echo Samsung S10+ - controllo USB durante l'avvio Ubuntu
echo Usa questo controllo con il telefono sul logo Samsung, non in TWRP.
echo Lascia USB collegato. Il programma legge solo informazioni sul PC.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check-boot-usb.ps1" -PackageRoot "%~dp0."
set "UT_BOOT_USB_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %UT_BOOT_USB_EXIT%
