# Programming on the main: the guard

Part C of [`RERUN_PLAN.md`](RERUN_PLAN.md). Every CV write on the main for speed matching goes
through `jmri/layouts/hart/scripts/speedmatch/pom_guard.py`; `pom_write.py` next to it is the
only thing that sends one, from inside the Pi's JMRI. Tests:
`jmri/layouts/hart/scripts/tests/test_pom_guard.py` (run by `./tools/check.sh` as part of
`unit-jmri`, and by CI).

## How a write reaches the decoder

On the CS-105 over LCC, JMRI 5.16's ops-mode programmer is an `OlcbProgrammer` built for one
DCC address. A write is an addressed memory-config write to that loco's train node
(`06.01.00.00.C0|hi.lo` for a long address) in space `0xF8`, CV n at offset n-1. Without
RailCom the CS-105 answers "no RailCom" and JMRI reports the write as OK, so OK means "sent";
the check is the re-measure, then a full read-back on the programming track at the end.
A POM read without RailCom fails the same way, so old values usually come from the ledger
or the roster.

## Checklist before an apply

1. PanelPro running on the Pi, the owner not operating, only the test loco on the track.
2. **Break every consist involving the target** with `cs105_consist.py ACTION = "detach"`,
   including any led by an address that is not in the roster. The guard queries every
   rostered loco's train node, but it cannot list consists led by unrostered addresses, so
   apply also needs `CONSISTS_BROKEN = True` as your confirmation (it is logged).
3. **Read the decoder on the programming track first** (the Part B preflight) and seed the
   ledger from that log, so old values are real reads, not roster values that may be
   decoder-definition defaults:
   `python3 pom_guard.py seed-ledger "CSX 2738" preflight.log` (on the Pi). The log is JSON
   (`{"roster_id": .., "cvs": {cv: value}}`) or text with one `CV<n> = <value>` per line.
   Without that, an apply that would take any old value from the roster needs
   `ROSTER_OLD_OK = True` (logged), and the plan marks those rows `roster (may be a default)`.
4. A dry run first (`APPLY = False`), and read its `PLAN` and `WARNING` lines.
5. Any CV29 change (speed table on or off) is done on the programming track, not here.

## What it refuses, and why

| Refused | Why |
|---|---|
| Any address not taken from the roster entry | the proposal names a roster id, never an address |
| Address 0 | the DCC broadcast address: every decoder on the track would take the write |
| Short address outside 1-127, long outside 1-10239 | not a valid DCC address (10239 is the NMRA long maximum JMRI uses) |
| Long/short flag that disagrees between `roster.xml`, the entry file, CV17/CV18 or CV29 bit 5 | the write would go to a different decoder than the one in the roster |
| Another roster entry with the same address number, or a `roster.xml` entry with no id | two locos would take the write, or the roster cannot be checked |
| CV19 not 0 in a read or the ledger | the decoder is in an advanced consist. A roster-only CV19 (or a short target equal to another entry's roster CV19) is a `WARNING`, because roster values can be defaults: BO 3545 and BO 6944 record 127 |
| A consist query that is missing, failed, has no line that is exactly `END`, does not cover every roster loco, or lists a node's listener indices other than exactly 0..count-1 once each | consist state unknown: fail closed. If the query has not finished within `CONSIST_TIMEOUT`, its thread may still be running in JMRI; wait until its log ends with `END`, then run again |
| A roster loco's train node that did not answer, unless its id is in `ABSENT_OK` | a silent lead could hold the target as a listener; `ABSENT_OK` entries are logged |
| The target not answering, having a listener, or being any node's listener | 2121 leads an LCC consist with 2738; break it first, make it again afterwards |
| Apply without `CONSISTS_BROKEN = True` | consists led by unrostered addresses are invisible to the query |
| CV29 | its real value cannot be read on the main; a whole-byte write could flip direction or address bits. Programming track only |
| Any other CV than 3, 4, 25, 66, 67-94, 95 | only momentum, speed table and trim are needed; CV1, 17, 18, 19 (addresses, consist) and CV8 (reset) are named in the refusal |
| A value (in a proposal, the ledger or `--reads`) that is not an integer 0-255 | a CV is one byte |
| A CV the ledger marks `unknown` | an earlier write timed out or failed, so the decoder may hold either value |
| A CV with no read, ledger or roster value | no rollback would be possible |
| A ledger file that exists but does not parse, or has bad entries (also for `clear-ledger`) | fail closed: it is never treated as empty |
| Apply with any old value from the roster, without `ROSTER_OLD_OK = True` | roster values may be decoder-definition defaults |
| A second run for the same loco while `<ledger dir>/<roster id>.lock` exists | one run per loco. A lock left by a crash is removed by hand, after checking the last run's log ends with `END` |
| Writing without `APPLY = True`, without a ledger, without a rollback path, or onto an existing rollback file | dry run is the default, and a rollback is never overwritten |

`pom_write.py` runs the guard's checks once, after the consist query and before it sends
anything (it refuses if the guard will not load), checks that JMRI's own roster entry agrees
with the files, uses only the CS-105 connection's `OlcbProgrammerManager`, and checks once that
the programmer it got is for the roster address. A read that times out aborts the run before
any write, since the read may still be in flight; a Java exception during a read aborts the
same way, and during a write it stops the run like a failed write. It never touches track power, emergency
stop, throttles, turnouts or MQTT.

## Old values, the ledger and skips

Without RailCom the roster is the only record of a decoder, and it goes stale as soon as a
write on the main lands. So the guard keeps a ledger per loco
(`~/speedmatch/ledger/<roster id>.json` on the Pi, set with `LEDGER_DIR`): per CV, the last
value read from the decoder (`read`) or sent with an OK reply (`sent`), or `unknown`. Every
entry carries a sequence number from a counter in the ledger, not a clock. Reads from any run,
dry runs included, are recorded there. Old values, for the plan and the rollback file, come in
this order, and each row says which (`old_source`):

1. `read`: read from the decoder in this run;
2. `ledger`: the ledger entry (read or sent);
3. `roster (may be a default)`: the roster's recorded value, which may be a decoder-definition
   default; an apply that uses one needs `ROSTER_OLD_OK = True`.

A CV is skipped as "already holds the value" only when it was read in this run.

## After the session: archive the ledger

The programming-track read-back at the end replaces the ledger. Read the full table back,
update the roster (Pi first, then sync), then move the ledger aside so the next run starts
from the roster:

```
python3 pom_guard.py archive-ledger "CSX 2738"        # moves CSX_2738.json to CSX_2738.<time>.json
```

## Recovering from a failed or timed-out write

A write that times out, fails or raises an exception stops the run and marks that CV
`unknown` in the ledger; the next run refuses it. At the stop the guard writes
`<ROLLBACK>.partial.json`: the old values of only the CVs this run wrote plus the one that
stopped it. (The full `<ROLLBACK>` file, written before the first write, is the rollback for a
run that completed.) The last log line before `END` names the steps, for example:

```
STOPPED at CV68 (timeout): it may hold 30 (new) or 27 (old) and is marked unknown in the
ledger. Writes before it stand. To roll back: 1) python3 pom_guard.py clear-ledger
"CSX 2738" CV68 --ledger-dir /home/pi/speedmatch/ledger  2) apply
/home/pi/speedmatch/rollback_2738_20261113T1500.json.partial.json as the proposal
```

1. `clear-ledger` (validated like any ledger load) accepts that CV68's value is not known.
   Its old value then comes from the roster, marked `roster (may be a default)`, so the
   rollback apply needs `ROSTER_OLD_OK = True`; or read CV68 on the programming track and
   `seed-ledger` instead.
2. Copy the partial rollback file to the Pi as `proposal.json` and drop the writer with
   `APPLY = True`, `CONSISTS_BROKEN = True` and a new `ROLLBACK` name.

Without step 1 the rollback is refused too, so an unknown CV is never planned by accident.

## Proposal file

```json
{"roster_id": "CSX 2738",
 "writes": [{"cv": 67, "value": 14}, {"cv": 68, "value": 28}],
 "note": "optional", "source": "optional"}
```

Inside a write only `cv`, `value`, `note` and `old_source` are allowed; other top-level keys
are ignored. A rollback file has the same shape, so it is applied the same way.

## Dry run on the Mac

With a consist query log from the Pi (`cs105_consist.py`, `ACTION = "query"`, every roster
loco's train node):

```
python3 jmri/layouts/hart/scripts/speedmatch/pom_guard.py proposal.json \
  --roster-dir <JMRI user files dir> --consist-log consist.log \
  [--absent-ok "NWR 06"] [--ledger-dir DIR] [--reads reads.json]
```

`--ledger-dir` defaults to `~/speedmatch/ledger`, the Pi's path. When no ledger is found there
it prints a `WARNING`: the Pi has its own ledger, so the Pi's plan may differ. It prints one `PLAN` line per CV (address, long/short, CV, old value and its source, new
value) or `REFUSED <reason>`. It never writes.

## Dry run and apply on the Pi

Copy the files, then drop the writer through `jmri_cmd_watcher` with its settings first (same
pattern as `tools/ops/cs105_roster_sync.sh`):

```
ssh pi 'mkdir -p /tmp/speedmatch /home/pi/speedmatch/ledger'
scp jmri/layouts/hart/scripts/speedmatch/pom_guard.py \
    jmri/layouts/hart/scripts/cs105_consist.py proposal.json pi:/tmp/speedmatch/
{ cat <<'EOF'
PROPOSAL = "/tmp/speedmatch/proposal.json"
GUARD_PATH = "/tmp/speedmatch/pom_guard.py"
CONSIST_SCRIPT = "/tmp/speedmatch/cs105_consist.py"
ABSENT_OK = []
CONSISTS_BROKEN = False
ROSTER_OLD_OK = False
LOGF = "/tmp/pom_write.log"
ROLLBACK = "/home/pi/speedmatch/rollback_2738_20261113T1500.json"
APPLY = False
EOF
  cat jmri/layouts/hart/scripts/speedmatch/pom_write.py; } > /tmp/pom_drop.py
scp /tmp/pom_drop.py pi:/tmp/jmri_cmd.py.tmp && ssh pi 'mv /tmp/jmri_cmd.py.tmp /tmp/jmri_cmd.py'
ssh pi cat /tmp/pom_write.log      # repeat until the last line is END
```

The consist query covers every roster loco, about 1.5 s each. A loco whose train node does not
answer (never driven since the CS-105 last started) refuses the run; add its roster id to
`ABSENT_OK` only when that loco is not on the layout. The dry run also saves
`<ROLLBACK>.dryrun`. To write, drop it again with `APPLY = True` and `CONSISTS_BROKEN = True`
(both exactly `True`, plus `ROSTER_OLD_OK = True` if any old value is from the roster) and a new `ROLLBACK` name. The log then shows `ROLLBACK written`, one
`WRITE CVn=v OK|FAILED|TIMEOUT` line per CV, and `DONE` or `STOPPED at ...`. Afterwards make
the consist again with `cs105_consist.py ACTION = "attach"`.
