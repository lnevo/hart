# Programming on the main: the guard

Part C of [`RERUN_PLAN.md`](../../../../../docs/jmri/speedmatching/RERUN_PLAN.md). Every CV write
on the main for speed matching goes through `pom_guard.py`; `pom_write.py` is the only thing
that sends one, from inside the Pi's JMRI. Tests: `jmri/layouts/hart/scripts/tests/test_pom_guard.py`
(run by `./tools/check.sh` as part of `unit-jmri`).

## How a write reaches the decoder

On the CS-105 over LCC, JMRI 5.16's ops-mode programmer is an `OlcbProgrammer` built for one
DCC address. A write is an addressed memory-config write to that loco's train node
(`06.01.00.00.C0|hi.lo` for a long address) in space `0xF8`, CV n at offset n-1. Without
RailCom the CS-105 answers "no RailCom" and JMRI reports the write as OK, so OK means "sent";
the check is the re-measure, then a full read-back on the programming track at the end.
A POM read without RailCom fails the same way, so old values usually come from the roster.

## What it refuses, and why

| Refused | Why |
|---|---|
| Any address not taken from the roster entry | the proposal names a roster id, never an address |
| Address 0 | the DCC broadcast address: every decoder on the track would take the write |
| Short address outside 1-127, long outside 1-10239 | not a valid DCC address (10239 is the NMRA long maximum JMRI uses) |
| Long/short flag that disagrees between `roster.xml`, the entry file, CV17/CV18 or CV29 bit 5 | the write would go to a different decoder than the one in the roster |
| Another roster entry with the same address number | two locos would take the write |
| Roster CV19 not 0, or a short target that is another entry's CV19 address | an advanced consist address reaches several decoders |
| A consist query that is missing, failed, incomplete, or where a node did not answer | consist state unknown: fail closed |
| Any listener on the target's train node or a partner's, or the target as anyone's listener | 2121 leads an LCC consist with 2738; break it first, make it again afterwards |
| A CV other than 3, 4, 25, 29, 66, 67-94, 95 | only momentum, speed table and trim are needed; CV1, 17, 18, 19 (addresses, consist) and CV8 (reset) are named in the refusal |
| A value that is not an integer 0-255 | a CV is one byte |
| CV29 changing any bit but bit 4 (16) | bit 4 turns the speed table on; the other bits are direction, address type, analog and so on |
| A CV with no read value and no roster value | no rollback would be possible |
| Writing without `APPLY = True`, without a rollback path, or onto an existing rollback file | dry run is the default, and a rollback is never overwritten |

`pom_write.py` runs every check itself before the first write (it refuses if the guard will
not load), checks that JMRI's own roster entry agrees with the file, uses only the CS-105
connection's `OlcbProgrammerManager`, checks the programmer's address before every write, and
stops at the first failed write. It never touches track power, emergency stop, throttles,
turnouts or MQTT.

## Proposal file

```json
{"roster_id": "CSX 2738",
 "writes": [{"cv": 67, "value": 14}, {"cv": 29, "value": 50}],
 "note": "optional", "source": "optional"}
```

Inside a write only `cv`, `value`, `note` and `old_source` are allowed. A rollback file has the
same shape, so it is applied the same way.

## Dry run on the Mac

With a consist query log from the Pi (`cs105_consist.py`, `ACTION = "query"`, both train nodes):

```
python3 jmri/layouts/hart/scripts/speedmatch/pom_guard.py proposal.json \
  --roster-dir <JMRI user files dir> --consist-log consist.log --partner "CSX 2121"
```

It prints one `PLAN` line per CV (address, long/short, CV, old value and where it came from,
new value) or `REFUSED <reason>`. It never writes.

## Dry run and apply on the Pi

PanelPro running on the Pi, the owner not operating, only the test loco on the track, and its
consist broken first (`cs105_consist.py ACTION = "detach"`). Copy the files, then drop the writer
through `jmri_cmd_watcher` with its settings first (same pattern as `tools/ops/cs105_roster_sync.sh`):

```
ssh pi 'mkdir -p /tmp/speedmatch /home/pi/speedmatch'
scp jmri/layouts/hart/scripts/speedmatch/pom_guard.py \
    jmri/layouts/hart/scripts/cs105_consist.py proposal.json pi:/tmp/speedmatch/
{ cat <<'EOF'
PROPOSAL = "/tmp/speedmatch/proposal.json"
GUARD_PATH = "/tmp/speedmatch/pom_guard.py"
CONSIST_SCRIPT = "/tmp/speedmatch/cs105_consist.py"
PARTNERS = ["CSX 2121"]
LOGF = "/tmp/pom_write.log"
ROLLBACK = "/home/pi/speedmatch/rollback_2738_20261113T1500.json"
APPLY = False
EOF
  cat jmri/layouts/hart/scripts/speedmatch/pom_write.py; } > /tmp/pom_drop.py
scp /tmp/pom_drop.py pi:/tmp/jmri_cmd.py.tmp && ssh pi 'mv /tmp/jmri_cmd.py.tmp /tmp/jmri_cmd.py'
ssh pi cat /tmp/pom_write.log      # repeat until the last line is END
```

Read the `PLAN` lines. To write, drop it again with `APPLY = True` (exactly `True`) and a new
`ROLLBACK` name. The log then shows `ROLLBACK written`, one `WRITE CVn=v OK|FAILED` line per
changed CV, and `DONE` or `STOPPED at CVn`. Afterwards make the consist again with
`cs105_consist.py ACTION = "attach"`.

`PARTNERS` must be set (`[]` when the loco never consists). A consist led by a loco that is not
in `PARTNERS` is only seen if that lead's train node is queried, so name every loco that has
led or followed the target.

## Rolling back

The rollback file is written before the first write and holds the old value of every planned
CV, each marked `old_source: "read"` (from the decoder) or `"roster"` (the roster's recorded
value, used when the decoder cannot be read on the main). Apply it as a proposal: copy it to
the Pi as `proposal.json` and drop the writer again with `APPLY = True` and a new `ROLLBACK`
name. Values marked `roster` are only as good as the roster entry; after any write on the main,
read the full table back on the programming track and update the roster (Pi first, then sync).
