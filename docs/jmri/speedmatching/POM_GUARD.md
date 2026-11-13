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

## What it refuses, and why

| Refused | Why |
|---|---|
| Any address not taken from the roster entry | the proposal names a roster id, never an address |
| Address 0 | the DCC broadcast address: every decoder on the track would take the write |
| Short address outside 1-127, long outside 1-10239 | not a valid DCC address (10239 is the NMRA long maximum JMRI uses) |
| Long/short flag that disagrees between `roster.xml`, the entry file, CV17/CV18 or CV29 bit 5 | the write would go to a different decoder than the one in the roster |
| Another roster entry with the same address number, or a `roster.xml` entry with no id | two locos would take the write, or the roster cannot be checked |
| Roster CV19 not 0, or a short target that is another entry's CV19 address | an advanced consist address reaches several decoders |
| A consist query that is missing, failed, incomplete, or does not cover every roster loco | consist state unknown: fail closed |
| A roster loco's train node that did not answer, unless its id is in `ABSENT_OK` | a silent lead could hold the target as a listener; `ABSENT_OK` entries are logged |
| The target not answering, having a listener, or being any node's listener | 2121 leads an LCC consist with 2738; break it first, make it again afterwards |
| A CV other than 3, 4, 25, 29, 66, 67-94, 95 | only momentum, speed table and trim are needed; CV1, 17, 18, 19 (addresses, consist) and CV8 (reset) are named in the refusal |
| A value (in a proposal, a reads file or `--reads`) that is not an integer 0-255 | a CV is one byte |
| CV29 changing any bit but bit 4 (16) | bit 4 turns the speed table on; the other bits are direction, address type, analog and so on |
| A CV the ledger marks `unknown` | an earlier write timed out or failed, so the decoder may hold either value |
| A CV with no read, ledger or roster value | no rollback would be possible |
| Writing without `APPLY = True`, without a ledger, without a rollback path, or onto an existing rollback file | dry run is the default, and a rollback is never overwritten |

`pom_write.py` runs every check itself before the first write (it refuses if the guard will
not load), checks that JMRI's own roster entry agrees with the file, uses only the CS-105
connection's `OlcbProgrammerManager`, and checks once that the programmer it got is for the
roster address. A read that times out aborts the run before any write, since the read may
still be in flight. It never touches track power, emergency stop, throttles, turnouts or MQTT.

## Old values, the ledger and skips

Without RailCom the roster is the only record of a decoder, and it goes stale as soon as a
write on the main lands. So the guard keeps a ledger per loco
(`~/speedmatch/ledger/<roster id>.json` on the Pi, set with `LEDGER_DIR`) of the last value
sent with an OK reply per CV, with a time. Old values, for the plan, the CV29 bit check and the
rollback file, come in this order, and each row says which (`old_source`):

1. `read`: read from the decoder in this run;
2. `reads_file`: a saved reads file (`<roster id>.reads.json`, written by any run that read
   every proposed CV, dry runs included) newer than the ledger entry for that CV;
3. `ledger`: the last value sent;
4. `roster`: the roster's recorded value.

A CV is skipped as "already holds the value" only when its old value was read in this run.
A write that times out or fails marks the CV `unknown` in the ledger and stops the run; the
log says the CV may have been written. The next run refuses that CV until a read newer than
the mark exists, or the operator clears it:

```
python3 pom_guard.py clear-ledger ~/speedmatch/ledger/CSX_2738.json 68
```

The programming-track read-back at the end of a session replaces the ledger: update the
roster from the read-back, then clear or move the ledger file so the roster is the record again.

## Proposal file

```json
{"roster_id": "CSX 2738",
 "writes": [{"cv": 67, "value": 14}, {"cv": 29, "value": 50}],
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
  [--absent-ok "NWR 06"] [--ledger CSX_2738.json] [--reads-file CSX_2738.reads.json]
```

It prints one `PLAN` line per CV (address, long/short, CV, old value and its source, new
value) or `REFUSED <reason>`. It never writes.

## Dry run and apply on the Pi

PanelPro running on the Pi, the owner not operating, only the test loco on the track, and its
consist broken first (`cs105_consist.py ACTION = "detach"`). Copy the files, then drop the writer
through `jmri_cmd_watcher` with its settings first (same pattern as `tools/ops/cs105_roster_sync.sh`):

```
ssh pi 'mkdir -p /tmp/speedmatch /home/pi/speedmatch/ledger'
scp jmri/layouts/hart/scripts/speedmatch/pom_guard.py \
    jmri/layouts/hart/scripts/cs105_consist.py proposal.json pi:/tmp/speedmatch/
{ cat <<'EOF'
PROPOSAL = "/tmp/speedmatch/proposal.json"
GUARD_PATH = "/tmp/speedmatch/pom_guard.py"
CONSIST_SCRIPT = "/tmp/speedmatch/cs105_consist.py"
ABSENT_OK = []
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
`ABSENT_OK` only when that loco is not on the layout. Read the `PLAN` lines; the dry run also
saves `<ROLLBACK>.dryrun`. To write, drop it again with `APPLY = True` (exactly `True`) and a new
`ROLLBACK` name. The log then shows `ROLLBACK written`, one `WRITE CVn=v OK|FAILED|TIMEOUT`
line per CV, and `DONE` or `STOPPED: ...`. Afterwards make the consist again with
`cs105_consist.py ACTION = "attach"`.

## Rolling back

The rollback file is written before the first write and holds the old value of every planned
CV with its `old_source`. Apply it as a proposal: copy it to the Pi as `proposal.json` and drop
the writer again with `APPLY = True` and a new `ROLLBACK` name. Values from `ledger` or `roster`
are only as good as that record; after any write on the main, read the full table back on the
programming track and update the roster (Pi first, then sync).
