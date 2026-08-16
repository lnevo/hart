@echo off
setlocal EnableExtensions
REM CATS Digicon fast launcher - accepts panel path as %1
REM launcher_version=20260811_0045

REM Prefer caller-supplied panel (CTC / ABS / ABS-RO wrappers pass this).
if not "%~1"=="" (
  set PANEL=%~1
) else (
  set PANEL=%USERPROFILE%\hart\cats\panels\HART_Master.xml
  if not exist "%PANEL%" set PANEL=%~dp0..\..\panels\HART_Master.xml
  if not exist "%PANEL%" set PANEL=%USERPROFILE%\Dropbox\HART_sync\panels\HART_Master.xml
  if not exist "%PANEL%" set PANEL=%USERPROFILE%\Dropbox\HART_sync\HART_Master.xml
)

REM Program Files JMRI first (not %%USERPROFILE%%\JMRI prefs folder)
set JMRI_HOME=
if exist "C:\Program Files\JMRI\LaunchJMRI.exe" set JMRI_HOME=C:\Program Files\JMRI
if "%JMRI_HOME%"=="" if exist "C:\Program Files (x86)\JMRI\LaunchJMRI.exe" set JMRI_HOME=C:\Program Files (x86)\JMRI
if "%JMRI_HOME%"=="" if exist "C:\JMRI\LaunchJMRI.exe" set JMRI_HOME=C:\JMRI
if "%JMRI_HOME%"=="" if exist "%USERPROFILE%\JMRI\LaunchJMRI.exe" set JMRI_HOME=%USERPROFILE%\JMRI
if "%JMRI_HOME%"=="" (
  echo JMRI not found. Run RUN_INSTALL.bat as Administrator.
  pause & exit /b 1
)

if not exist "%JMRI_HOME%\cats.jar" (
  if exist "%USERPROFILE%\Dropbox\HART_sync\cats.jar" copy /Y "%USERPROFILE%\Dropbox\HART_sync\cats.jar" "%JMRI_HOME%\cats.jar" >nul
  if not exist "%JMRI_HOME%\cats.jar" if exist "%USERPROFILE%\JMRI\cats.jar" copy /Y "%USERPROFILE%\JMRI\cats.jar" "%JMRI_HOME%\cats.jar" >nul
)
if not exist "%JMRI_HOME%\cats.jar" (
  echo cats.jar missing in "%JMRI_HOME%". Run RUN_INSTALL.bat as Administrator.
  pause & exit /b 1
)

REM CATS requires crandic.gif next to JMRI (NPE in Apps.statusPanel if missing)
if exist "%USERPROFILE%\Dropbox\HART_sync\crandic.gif" (
  if not exist "%JMRI_HOME%\crandic.gif" copy /Y "%USERPROFILE%\Dropbox\HART_sync\crandic.gif" "%JMRI_HOME%\crandic.gif" >nul 2>&1
  if not exist "%USERPROFILE%\JMRI\crandic.gif" (
    mkdir "%USERPROFILE%\JMRI" 2>nul
    copy /Y "%USERPROFILE%\Dropbox\HART_sync\crandic.gif" "%USERPROFILE%\JMRI\crandic.gif" >nul 2>&1
  )
  if exist "%USERPROFILE%\JMRI\My_JMRI_Railroad.jmri\" copy /Y "%USERPROFILE%\Dropbox\HART_sync\crandic.gif" "%USERPROFILE%\JMRI\My_JMRI_Railroad.jmri\crandic.gif" >nul 2>&1
)

if not exist "%PANEL%" (
  echo Panel missing: %PANEL%
  pause & exit /b 1
)

REM Clean up fake Digicon "profile" from earlier bug
if exist "%USERPROFILE%\JMRI\HART_sheet_West_Yard.jmri" rmdir /S /Q "%USERPROFILE%\JMRI\HART_sheet_West_Yard.jmri" 2>nul
if exist "%APPDATA%\JMRI\HART_sheet_West_Yard.jmri" rmdir /S /Q "%APPDATA%\JMRI\HART_sheet_West_Yard.jmri" 2>nul

set IDFILE=%USERPROFILE%\hart\jmri_profile_id.txt
set RESOLVER=%USERPROFILE%\Dropbox\HART_sync\resolve_jmri_profile.ps1
if not exist "%RESOLVER%" set RESOLVER=%USERPROFILE%\hart\resolve_jmri_profile.ps1
set PATCHMQTT=%USERPROFILE%\Dropbox\HART_sync\patch_windows_mqtt.ps1
if not exist "%PATCHMQTT%" set PATCHMQTT=%USERPROFILE%\hart\patch_windows_mqtt.ps1
set KILLPS=%USERPROFILE%\Dropbox\HART_sync\kill_cats.ps1
if not exist "%KILLPS%" set KILLPS=%USERPROFILE%\hart\kill_cats.ps1

REM Quietly stop any prior Crandic (no pause)
if exist "%KILLPS%" powershell -NoProfile -ExecutionPolicy Bypass -File "%KILLPS%" >nul 2>&1

REM Cache profile id (fast). Force refresh only if missing.
if not exist "%IDFILE%" (
  if not exist "%RESOLVER%" (
    echo Missing resolve_jmri_profile.ps1
    pause & exit /b 1
  )
  powershell -NoProfile -ExecutionPolicy Bypass -File "%RESOLVER%" -OutFile "%IDFILE%" -SetActive
)

set JMRI_PROFILE=
if exist "%IDFILE%" set /p JMRI_PROFILE=<"%IDFILE%"
if "%JMRI_PROFILE%"=="" (
  echo Empty profile id. Deleting cache and retrying...
  del /f /q "%IDFILE%" 2>nul
  powershell -NoProfile -ExecutionPolicy Bypass -File "%RESOLVER%" -OutFile "%IDFILE%" -SetActive -Force
  set /p JMRI_PROFILE=<"%IDFILE%"
)
if "%JMRI_PROFILE%"=="" (
  echo Could not resolve My JMRI Railroad profile id.
  pause & exit /b 1
)

REM Ensure MQTT points at Pi 192.168.137.2 (avoids multi-minute hang)
if exist "%PATCHMQTT%" powershell -NoProfile -ExecutionPolicy Bypass -File "%PATCHMQTT%"

cd /d "%JMRI_HOME%"
echo JMRI_HOME=%JMRI_HOME%
echo JMRI_PROFILE=%JMRI_PROFILE%
echo PANEL=%PANEL%
echo Starting CATS...

REM Lock config to CatsConfig.xml so Digicon XML is layout-only, not a new profile
LaunchJMRI.exe /profile %JMRI_PROFILE% -J-Dorg.jmri.Apps.configFilename=CatsConfig.xml --cp:a=cats.jar cats.apps.Crandic "%PANEL%"
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo LaunchJMRI exited %RC%
  pause
)
exit /b %RC%
