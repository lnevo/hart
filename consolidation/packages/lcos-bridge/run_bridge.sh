#!/usr/bin/env bash
# Run LCOS serial bridge from consolidation workspace (foreground).
set -euo pipefail

PKG="$(cd "$(dirname "$0")" && pwd)"
CON="$(cd "$PKG/../.." && pwd)"
LCOS="$CON/external/lcos-bridge"

COM="${HART_LCOS_COM:-/dev/ttyUSB0}"
BROKER="${HART_MQTT_BROKER:-minipc-e5h6x.local}"
PORT="${HART_MQTT_PORT:-1883}"

cd "$LCOS"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "LCOS bridge: $COM -> mqtt://$BROKER:$PORT (foreground)"
exec .venv/bin/python -u serial_to_mqtt.py --com "$COM" --broker "$BROKER" --mqtt-port "$PORT" --verbose
