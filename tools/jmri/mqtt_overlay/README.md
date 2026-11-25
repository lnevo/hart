# JMRI MQTT race overlay

JMRI 5.16's `MqttAdapter` with the listener-race fix from [JMRI/JMRI#16004](https://github.com/JMRI/JMRI/pull/16004), loaded ahead of `jmri.jar` on every host until JMRI ships the fix in a release the hosts run ([ADR-034](../../../wiki/decisions/ADR-034-jmri-mqtt-race-overlay.md)).

- `MqttAdapter.java`: JMRI 5.16 source plus the #16004 hunks only (same as [`mqtt-adapter-fix.diff`](../../../docs/jmri/mqtt-adapter-fix.diff) without the 5.19 UTF-8 lines). JMRI's GPL header is kept.
- `hart-mqtt-race-fix.jar`: the compiled class, committed. `./build.sh` rebuilds it from the Mac's `/Applications/JMRI`; `./build.sh --check` fails if it no longer matches the source.
- `install_overlay.py`: copies the jar into the JMRI settings folder and adds `--cp:p=<jar>` to `jmri.conf`, keeping its other options. Only over JMRI 5.16.0 `909e15189e`; on any other build it takes the overlay out. The deploy runs it on the Mac (`~/Library/Preferences/JMRI`), the Pi (`~/.jmri`) and Windows (`%USERPROFILE%\JMRI`). `--remove --settings-dir <dir>` takes it out by hand.

To see it is loaded, the running java's command line has `hart-mqtt-race-fix.jar` in its `-cp`, and a dropped connection at start no longer shows `Can't subscribe`.
