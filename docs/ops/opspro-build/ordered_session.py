"""Ordered session on copies, through the plugin's own JMRI worker: D749 alone, then NVL and CK1, then the STG
trains, then D749 again (next session). Each job builds and terminates its trains and saves to a kept folder that
the next job starts from. The real Operations folder is never touched."""
import json, shutil, sys, collections
from pathlib import Path
sys.path.insert(0, "/Users/lnevo/.claude/plugins/cache/model-railroad-skills/operations-pro/0.1.2/servers")
import ops_jmri

SRC = Path("/Users/lnevo/hart/jmri/layouts/hart/operations")
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
steps = [("1_d749", ["D749"]), ("2_nvl_ck1", ["NVL", "CK1"]), ("3_stg", ["STG-DEMMLER", "STG-SCULLY"]), ("4_d749_next", ["D749"]),
         ("5_nvl_ck1_next", ["NVL", "CK1"])]
source = SRC
summary = {}
for name, only in steps:
    keep = OUT / name; keep.mkdir(exist_ok=True)
    result = ops_jmri.run_worker(source, {"build": True, "only": only, "terminate": True, "save": True}, keep=keep)
    rows = {}
    for train, row in result["builds"].items():
        picks = collections.Counter()
        for c in row["placed"]:
            picks[c["location"] + " / " + c["track"]] += 1
        text = row.pop("report_text", ""); row.pop("report_tail", "")
        (keep / f"report_{train}.txt").write_text(text)
        rows[train] = {"built": row["built"], "failed": row["failed"], "status": row["message"], "engines": row["engines"],
                       "departs": row["departure_track"], "cars": row["cars"], "set_outs_by_track": dict(picks),
                       "terminated": row.get("terminated")}
    summary[name] = {"trains": rows, "log_errors": result["log_errors"]}
    print("==", name, {t: (r["status"], len(r["cars"])) for t, r in rows.items()}, "log errors:", len(result["log_errors"]), flush=True)
    source = keep
json.dump(summary, open(OUT / "summary.json", "w"), indent=1)
