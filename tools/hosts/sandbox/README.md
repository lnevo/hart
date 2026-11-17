# Sandbox PanelPro runs

Rehearse Stage 1, NX Discover and take panel pictures without touching the layout, the live profile or
`~/JMRI_UserFiles`. Used for the Layout Editor cut-over (2026-11-16) and every rehearsal since.

## Set up once per sandbox folder

Pick a folder outside the repo (a session scratchpad is fine) and call it `HART_SANDBOX`.

1. Copy the live profile: `cp -R ~/Library/Preferences/JMRI/My_JMRI_Railroad.jmri "$HART_SANDBOX/HARTSandbox.jmri"`.
2. Give it its own user files: in `HARTSandbox.jmri/profile/profile.properties` and every node folder's
   `profile.properties`, set `jmri-implementation.user-files=$HART_SANDBOX/uf/`. Copy into `uf/` the user files the
   run needs: `jython/`, `dispatcher/traininfo/`, `resources/` (panel backdrop, buttons), `cats/panels/`, and `ctc/icons/` from
   `jmri/layouts/hart/ctc/icons/` (without it the USS CTC panel stops the load with an "Icon Not Found" dialog per turnout icon).
3. Point its MQTT connection (M2) at a local broker: host 127.0.0.1, port 18830. JMRI skips Start Up when M2 cannot
   connect, so the broker must be running.
4. Broker config `$HART_SANDBOX/broker/mosquitto.conf`: `listener 18830 127.0.0.1`, `allow_anonymous true`,
   `persistence false`. Start it with `/opt/local/sbin/mosquitto -c "$HART_SANDBOX/broker/mosquitto.conf" -d`;
   stop it with `pkill -f "$HART_SANDBOX/broker/mosquitto.conf"`.

`tools/hosts/panelpro_session.sh` (its header) backs the profile up and restores it after every run.

## Runs

The PanelPro wrappers load the tables of the checkout they run from, so use a throwaway worktree whose
`jmri/layouts/hart/output/tables.xml` is the candidate (never commit it).

- Stage 1: `source tools/hosts/sandbox/sandbox_env.sh; jmri/layouts/hart/scripts/run_panelpro_stage1.sh`
- NX Discover: remove `<layoutPanel>` under `<entryexitpairs>` first (Discover only adds), then
  `jmri/layouts/hart/scripts/run_nx_discover.sh`. Its "MQTT to the Pi broker" line is fixed text; the sandbox
  profile talks to the local broker.
- Panel picture: `tools/hosts/sandbox/panel_snapshot.sh <checkout> <out.png>`, which writes the whole panel as
  PanelPro paints it. Compare signal logic by the stored pairs (`signalmastlogic` source and destination) against
  the live tables.

CATS on the sandbox profile: `JMRI_PROFILE=$HART_SANDBOX/HARTSandbox.jmri CATS_LAUNCH_VIA=direct
cats/scripts/launch_cats.sh <desk.xml>`. Check its About box shows the sandbox profile and 127.0.0.1 before
trusting a screenshot.
