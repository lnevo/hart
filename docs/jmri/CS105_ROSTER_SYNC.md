# Roster to CS-105 sync

Copy the JMRI roster (names, DCC addresses, function labels) into the TCS CS-105 command station so UWT-100 throttles see every locomotive with its labels.

## What you can do

```
tools/ops/cs105_roster_sync.sh                  # show the plan, write nothing
tools/ops/cs105_roster_sync.sh --apply          # create missing trains, refresh labels
tools/ops/cs105_roster_sync.sh --apply --only 1993,572
tools/ops/cs105_roster_sync.sh --apply --rename # also rename trains the CS-105 already has
tools/ops/cs105_roster_sync.sh --apply --rename --names road   # names as "Road Number", e.g. PRC 4678
```

Run it from the Mac while the Pi's JMRI is up. It does not need PanelPro on the Mac, and it does not touch turnouts, signals or MQTT.

The plan lists one line per roster entry: CREATE (the CS-105 has no train for that address), UPDATE (it has one; labels and description are refreshed) or SKIP. Train entries on the CS-105 that have no roster entry are listed as KEEP and never changed.

## How it works

- The roster is read on the Pi, from JMRI's own roster index and locomotive files. The Pi roster is the master copy; the Mac and Windows copies are refreshed from it.
- Each roster entry maps to a CS-105 virtual train node. Short address n is node `06.01.00.00.00.nn`; long address n is `06.01.00.00.(C0+high).low`. JMRI uses the same mapping.
- A missing train is created with the OpenLCB Train Search Protocol: an Identify Producer message for event `09.00.99.FF` + the address digits + flags Allocate, Exact, Address-only, DCC and (for long addresses) Force-long. The CS-105 answers by creating the train node.
- Labels are written through the train node's configuration (CDI), the same fields JMRI's DecoderPro menu "File > Export > Roster entry to TCS CS-105" writes: `Train.User Description`, and for F1 to F28 `Train.Functions(n).Display`, `Momentary` and `Description` (n = function number minus one; F0 is the headlight). A label JMRI knows as an icon (Bell, Horn, Dimmer and so on) becomes the icon code; any other text is sent as plain text.
- `Train.Name` is set only for trains the sync creates, or for all selected trains with `--rename`. The default name is the roster ID; `--names road` uses "Road Number" from the roster (an entry with no road data falls back to its ID). Since 2026-11-07 every roster ID is already "Road Number" (for example "BO 572", "NWR 06"), so both schemes give the same name. WiThrottle and Engine Driver list the roster ID, which is why the ID carries the road name. After adding a roster entry, run `jmri/layouts/hart/scripts/roster_rename_road_ids.py` through the Pi's JMRI (same watcher channel) so the new ID follows the scheme, then run this sync.
- The CS-105 keeps a train across a restart only once it has a `Train.Name`. A train that was only selected on a throttle, or that received labels but no name, is a live node that vanishes at the next restart (seen 2026-11-07: 1993, 2091, 2121 and 9602 came back nameless until `--rename` set their names). Trains the sync creates always get a name, so they persist.
- `Train.User Description` is written from the roster comment only when the comment is not empty, so a description typed on a throttle survives an entry with no comment (since 1.0.0 of the public script).
- Before planning, the script asks every LCC node to announce itself and looks for the CS-105 by its SNIP model name. The second line of the output names it, or says `CS-105 NOT FOUND`; in that case `--apply` is refused and nothing is written. (A down CS-105 looks like an empty one: on 2026-11-08 the plan offered to create all 17 locos.) A second apply while one is running is also refused.
- Consist Behavior bits are left as they are. JMRI derives them from decoder CVs, which this script does not read.

## Restarting the CS-105

```
tools/ops/cs105_reboot.sh
```

Sends the CS-105 the OpenLCB Reset/Reboot datagram through the Pi's JMRI, waits for it to come back and lists every node on the bus, naming the ones that disappeared. Use it after deleting trains from the CS-105 roster (`Train.Delete From Roster?`), because deleted trains stay on the bus as live nodes until the command station restarts. Track power drops for a few seconds, so run it only when nothing is moving.

## Doing it by hand in JMRI

DecoderPro can do one entry at a time, but only if the CS-105 already has a train for that address. Open the roster entry, then File > Export > "Roster entry to TCS CS-105". If the train does not exist yet, select the address once on a UWT-100 (which creates it), then export. The sync script does both steps for every entry.

## Where the pieces live

- Script that runs inside JMRI: `external/jmri-cs105-roster-sync/cs105_roster_sync.py`, a submodule of the public repo [lnevo/jmri-cs105-roster-sync](https://github.com/lnevo/jmri-cs105-roster-sync) (Jython 2.7 and CPython 3). Change it there, then move the submodule pointer. Run from PanelPro's Scripting menu it opens a window that plans first; through the wrapper it runs without a window.
- Roster ID renamer (Jython, runs in the Pi's JMRI): `jmri/layouts/hart/scripts/roster_rename_road_ids.py`.
- Restart script and wrapper: `jmri/layouts/hart/scripts/cs105_reboot.py`, `tools/ops/cs105_reboot.sh`.
- Mac wrapper: `tools/ops/cs105_roster_sync.sh`. It drops the script into the Pi's `jmri_cmd_watcher.py` channel and prints the result.
- Tests: in the submodule, `python3 -m unittest discover -s tests` (CI runs them under Python 3 and Jython 2.7).
- Offline plan from a roster folder (no device): `python3 external/jmri-cs105-roster-sync/cs105_roster_sync.py <folder with roster.xml and roster/> --values`.

Sources: OpenLCB Train Search Protocol Standard (2024-07-22) in the openlcb/documents repo; JMRI 5.16 `jmri.jmrit.symbolicprog.TcsUploadAction` and `TcsExportAction`; JMRI help page "OpenLCB on TCS Hardware".
