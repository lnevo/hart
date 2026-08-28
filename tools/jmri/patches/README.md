# JMRI/CATS startup overlays

`hart-startup-guard.jar` is prepended on CATS launch (`--cp:p`) so it wins over
`jmri.jar` / `cats.jar`. The build script also writes `~/Library/Preferences/JMRI/jmri.conf`
so PanelPro.app gets the MQTT overlay. Rebuild:

```bash
./tools/jmri/patches/build_startup_guard.sh
```

- **MqttAdapter** — table load vs retained MQTT used to throw
  `ConcurrentModificationException` on the Paho thread, drop the broker
  connection, then log `ERROR Can't subscribe` for every remaining bean.
  Also **does not publish** to `_discard/**` (retired JMRI sensor send
  template `11.3`). Clear leftover retain with
  `python3 cats/scripts/clear_mqtt_cmd_sensor_retain.py`.
- **BlkEdge / Track** — stock CATS keeps the first Block and warns on a second
  (occupancy cuts, plant frogs). Skip the warn; do not change which Block wins.
- **OperationsClient** — skip the unused loopback ops-server probe (no
  `127.0.0.1: Connection refused`).

Does not publish MQTT or alter CATS geometry. Stock jars stay untouched.
