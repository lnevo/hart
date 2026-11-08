@echo off
REM Opens one Windows Terminal window with two tabs at logon:
REM   Bridge   - run_serial_mqtt.cmd verbose (foreground, Ctrl+C to stop)
REM   MQTT sub - sub.bat (mosquitto_sub on #)
REM Install: copy into shell:startup on the layout mini PC (runs after you log in, never before).
REM Remove:  delete it from shell:startup.

set "LCOS=%USERPROFILE%\Documents\LCOS_ESP32_MQTT_Client"

REM Give the network and the Nano's USB COM port time to come up after boot.
timeout /t 20 /nobreak >nul

wt -w hart-bridge new-tab --title "Bridge" --suppressApplicationTitle -d "%LCOS%" cmd /k run_serial_mqtt.cmd verbose ; new-tab --title "MQTT sub" --suppressApplicationTitle -d "%LCOS%" cmd /k sub.bat ; focus-tab -t 0
