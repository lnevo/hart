@echo off
setlocal
set PANEL=%USERPROFILE%\hart\cats\panels\HART_Master_CTC_hold.xml
if not exist "%PANEL%" set PANEL=%USERPROFILE%\Dropbox\HART_sync\panels\HART_Master_CTC_hold.xml
if not exist "%PANEL%" set PANEL=%USERPROFILE%\Dropbox\HART_sync\HART_Master_CTC_hold.xml
echo PANEL=%PANEL%
if not exist "%PANEL%" (
  echo ERROR: panel not found
  pause
  exit /b 1
)
call "%USERPROFILE%\hart\cats\scripts\windows\launch_cats_desktop.bat" "%PANEL%"
