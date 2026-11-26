# Pipeline 9 — LCOS Nano firmware

Flash the Arduino Nano that bridges LCOS radio (nRF24) to USB serial MQTT lines.

**Status:** Live. Repo: [`LCOS_ESP32_MQTT_Client`](https://github.com/lnevo/LCOS_ESP32_MQTT_Client) (folder name is historical; hardware is Nano).

**API truth:** `lcos/lcos.h`, `lcos/lcos.cpp`, `reference/` — do not edit vendor `lcos/` or `reference/` unless merging an official drop.

## Inputs

- `LCOS_ESP32_MQTT_Client.ino` — RF channel, `thisNode`
- `lcos_mqtt_bridge.cpp` — `kSubscribeDisplayNodes[]` (event **125** to those display nodes)

## Outputs

- Firmware on the Nano. Boot should log `Subscription accepted` per node. Host `RESUBSCRIBE` re-emits 125.

## Run

Configure nodes, commit them in the bridge repo, then on the Pi (the Nano is on its USB):

```bash
ssh pi@rpi-jmri.local
cd ~/lcos-bridge && git pull
./bridge flash     # compile with arduino-cli, stop the bridge, upload to /dev/lcos-nano, start it again
./bridge log       # look for `Subscription accepted` per node
```

`./bridge compile` builds without uploading. The Pi's userland is 32-bit (armhf), so it uses the ARMv7 arduino-cli; the Arduino IDE is not needed. The bridge runs as the `lcos-bridge` systemd service; the operating flag applies to flashing, since it is the Pi.

Detail: that repo’s `README.md`, `docs/serial_mqtt_linux.md`.

