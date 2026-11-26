# LCOS bridge package

**Source:** [`../../external/lcos-bridge/`](../../../external/lcos-bridge) (git submodule)

Includes:
- **`lcos-bridge.ino`** — Nano firmware (`./bridge flash` on the Pi; no IDE needed)
- **`serial_to_mqtt.py`** — host COM ↔ MQTT bridge (**part of this package**)
- **`bridge`** (`scripts/linux/bridge.sh`) — service control on the Pi; **`run_serial_mqtt.sh`** for lab runs

## Prerequisites

1. MQTT broker running — [`../infra/mqtt-broker/README.md`](../infra/mqtt-broker/README.md)
2. USB serial to Nano (250000 baud)
3. Python 3 + `requirements.txt` in submodule

## Layout host: the Pi (since 2026-11-21)

The bridge Nano is on the Pi's USB, and the bridge runs there as the `lcos-bridge` systemd service from `~/lcos-bridge` (a clone of the bridge repo), next to Mosquitto (`127.0.0.1`). Setup, flashing and the service are in the bridge repo's [`docs/serial_mqtt_linux.md`](../../../external/lcos-bridge/docs/serial_mqtt_linux.md) (sections 6 and 7).

```bash
ssh pi@rpi-jmri.local
cd ~/lcos-bridge
./bridge status          # state, /dev/lcos-nano, last log lines
./bridge log             # follow; Ctrl+C stops the tail only
./bridge restart
./bridge flash           # after a firmware change: compile, stop, upload, start
```

The Windows mini PC no longer runs the bridge; it keeps the LCOS MASTER Nano (COM7).

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
