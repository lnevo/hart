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

- The roster is read on the Pi, from JMRI's own roster index and locomotive files. The Pi roster is the full one; the Mac copy lacks 2121.
- Each roster entry maps to a CS-105 virtual train node. Short address n is node `06.01.00.00.00.nn`; long address n is `06.01.00.00.(C0+high).low`. JMRI uses the same mapping.
- A missing train is created with the OpenLCB Train Search Protocol: an Identify Producer message for event `09.00.99.FF` + the address digits + flags Allocate, Exact, Address-only, DCC and (for long addresses) Force-long. The CS-105 answers by creating the train node.
- Labels are written through the train node's configuration (CDI), the same fields JMRI's DecoderPro menu "File > Export > Roster entry to TCS CS-105" writes: `Train.User Description`, and for F1 to F28 `Train.Functions(n).Display`, `Momentary` and `Description` (n = function number minus one; F0 is the headlight). A label JMRI knows as an icon (Bell, Horn, Dimmer and so on) becomes the icon code; any other text is sent as plain text.
- `Train.Name` is set only for trains the sync creates, or for all selected trains with `--rename`. The default name is the roster ID; `--names road` uses "Road Number" from the roster (an entry with no road data falls back to its ID). 4678 was renamed "PRC 4678" this way on 2026-11-07.
- Consist Behavior bits are left as they are. JMRI derives them from decoder CVs, which this script does not read.

## Doing it by hand in JMRI

DecoderPro can do one entry at a time, but only if the CS-105 already has a train for that address. Open the roster entry, then File > Export > "Roster entry to TCS CS-105". If the train does not exist yet, select the address once on a UWT-100 (which creates it), then export. The sync script does both steps for every entry.

## Where the pieces live

- Script that runs inside JMRI: `jmri/layouts/hart/scripts/cs105_roster_sync.py` (Jython 2.7 and CPython 3).
- Mac wrapper: `tools/ops/cs105_roster_sync.sh`. It drops the script into the Pi's `jmri_cmd_watcher.py` channel and prints the result.
- Tests: `jmri/layouts/hart/scripts/tests/test_cs105_roster_sync.py`.
- Offline plan from a roster folder (no device): `python3 jmri/layouts/hart/scripts/cs105_roster_sync.py <folder with roster.xml and roster/> --values`.

Sources: OpenLCB Train Search Protocol Standard (2024-07-22) in the openlcb/documents repo; JMRI 5.16 `jmri.jmrit.symbolicprog.TcsUploadAction` and `TcsExportAction`; JMRI help page "OpenLCB on TCS Hardware".
