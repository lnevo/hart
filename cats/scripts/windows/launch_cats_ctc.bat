@echo off
setlocal
set PANEL=%USERPROFILE%\JMRI_UserFiles\cats\panels\HART_CTC.xml
if not exist "%PANEL%" set PANEL=%USERPROFILE%\Dropbox\HART_sync\panels\HART_CTC.xml
if not exist "%PANEL%" set PANEL=%USERPROFILE%\Dropbox\HART_sync\HART_CTC.xml
echo PANEL=%PANEL%
if not exist "%PANEL%" (
  echo ERROR: panel not found
  pause
  exit /b 1
)
call "%~dp0launch_cats_desktop.bat" "%PANEL%"
