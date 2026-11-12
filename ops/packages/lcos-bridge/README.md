# LCOS bridge package

**Source:** [`../../external/lcos-bridge/`](../../../external/lcos-bridge) (git submodule)

Includes:
- **`lcos-bridge.ino`** — Nano firmware (Arduino IDE: open the submodule folder)
- **`serial_to_mqtt.py`** — host COM ↔ MQTT bridge (**part of this package**)
- **`run_serial_mqtt.cmd`** / **`.sh`** — operator launchers

## Prerequisites

1. MQTT broker running — [`../infra/mqtt-broker/README.md`](../infra/mqtt-broker/README.md)
2. USB serial to Nano (250000 baud)
3. Python 3 + `requirements.txt` in submodule

## Windows deploy (layout mini PC)

From the repo:

```powershell
cd path\to\hart\external\lcos-bridge
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -u serial_to_mqtt.py --com COM3 --broker 10.0.0.150 --verbose
```

Or use the bridge's own launcher from that folder: `run_serial_mqtt.cmd verbose` (Windows) or `run_serial_mqtt.sh` (Mac/Linux).

**Foreground only** — operator owns the process; Ctrl+C to stop. Do not run hidden/detached.

### Start at logon (two tabs)

[`windows/start_bridge_tabs.cmd`](windows/start_bridge_tabs.cmd) opens one Windows Terminal window after you log in. It has a **Bridge** tab (`run_serial_mqtt.cmd verbose`) and an **MQTT sub** tab (`sub.bat`), both from `%USERPROFILE%\Documents\LCOS_ESP32_MQTT_Client`. It waits 20 s first so the network and COM port are ready. Install it by copying it into `shell:startup` (Win+R, `shell:startup`). Remove it by deleting it from that folder. It never runs before logon.

## Mac lab

```bash
cd external/lcos-bridge
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -u serial_to_mqtt.py --com /dev/tty.usbserial-* --broker "$HART_MQTT_BROKER" --verbose
```

## Firmware flash

Open `external/lcos-bridge/` in Arduino IDE (`lcos-bridge.ino` matches folder name).

Windows helper: `external/lcos-bridge/scripts/windows/flash_nano.py`

## Smoke test

[`wiki/pipelines/mqtt-mimic.md`](../../../wiki/pipelines/mqtt-mimic.md#bridge-smoke-test)
