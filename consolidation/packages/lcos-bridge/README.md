# LCOS bridge package (consolidation)

**Source:** [`../../external/lcos-bridge/`](../../external/lcos-bridge/) (git submodule)

Includes:
- **`lcos-bridge.ino`** — Nano firmware (Arduino IDE: open the submodule folder)
- **`serial_to_mqtt.py`** — host COM ↔ MQTT bridge (**part of this package**)
- **`run_serial_mqtt.cmd`** / **`.sh`** — operator launchers

## Prerequisites

1. MQTT broker running — [`../infra/mqtt-broker/README.md`](../infra/mqtt-broker/README.md)
2. USB serial to Nano (250000 baud)
3. Python 3 + `requirements.txt` in submodule

## Windows deploy (layout mini PC)

From consolidation workspace:

```powershell
cd path\to\hart\consolidation\external\lcos-bridge
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -u serial_to_mqtt.py --com COM3 --broker minipc-e5h6x.local --verbose
```

Or use the consolidation wrapper (sets broker from env):

```powershell
..\..\packages\lcos-bridge\run_bridge.ps1
```

**Foreground only** — operator owns the process; Ctrl+C to stop. Do not run hidden/detached.

## Mac lab

```bash
cd consolidation/external/lcos-bridge
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -u serial_to_mqtt.py --com /dev/tty.usbserial-* --broker "$HART_MQTT_BROKER" --verbose
```

## Firmware flash

Open `consolidation/external/lcos-bridge/` in Arduino IDE (`lcos-bridge.ino` matches folder name).

Windows helper: `scripts/windows/flash_nano.py`

## Tier B smokes

[`../../cross-repo/lcos/TIER_B.md`](../../cross-repo/lcos/TIER_B.md)
