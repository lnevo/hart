"""build_main_upper_masts.py [--check]

Write jmri/layouts/hart/data/schematic/main_upper_masts.csv: the main and upper levels' control-point masts, one row
per mast, from device_map_main_upper.csv (its mast and head rows, owner plan 2026-11-16). Each mast is a home signal:
it faces the track its notes name ("home signal from Track X") and protects the OS block of the switch its comment
names ("CP n | Switch N"), so it stands at the boundary between the two. L masts are westward, R masts eastward
(ADR-022). `leg` tells apart two masts with one facing and protected block (Switch 107's balloon loop): the A mast
stands on the switch's normal leg, the B mast on its diverging leg (owner, 2026-11-16).

Until the cut-over they are internal: each head's system name is the device map's with a 9 after "IH" (IH3332 ->
IH93332), and each mast's system name names those heads. signal_coordinator.py enrols and publishes a head only when
its name is IH<node x 100 + signal 32..47> with an octal node (_is_lcos_ih_sys), and "933" is no octal node, so none
of these reaches MQTT or the field (build_layout_le.py checks it with the coordinator's own test).

--check regenerates in memory and exits 1 if the file differs.
"""
import csv
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA and hartlib paths
from hartlib import level_masts  # noqa: E402  the file, its fields and the internal head rule

DEVICE_MAP = pd.DATA / "device_map_main_upper.csv"
OUT = level_masts.PATH
LEGS = {"A": "normal", "B": "diverging"}       # of two masts sharing a block pair, by letter (owner, 2026-11-16)


def internal(head_sys: str, mast: str) -> str:
    """The internal name of a device-map head (hartlib.level_masts.internal_head); stops naming the head and mast on
    anything but IH and four digits, which the recognisers would not take."""
    try:
        return level_masts.internal_head(head_sys)
    except ValueError as exc:
        raise SystemExit(f"{DEVICE_MAP.name}: mast {mast}: {exc}") from None


def build() -> str:
    """The file's text. Stops on a mast whose comment names no switch, whose notes name no facing track, whose
    system name is not a SignalHeadSignalMast of the device map's heads, or a LEGS mast the map does not have."""
    rows = list(csv.DictReader(DEVICE_MAP.open(newline="", encoding="utf-8")))
    heads = {r["system_name"]: r["user_name"] for r in rows if r["layer"] == "head"}
    out_rows = []
    for r in rows:
        if r["layer"] != "mast":
            continue
        name = r["user_name"]
        sw = re.fullmatch(r".*\| Switch (\d+)", r["comment"].strip())
        fac = re.fullmatch(r"home signal from (Track .+)", r["notes"].strip())
        sysm = re.fullmatch(r"IF\$shsm:(\w+):([\w-]+)((?:\(IH\d+\))+)", r["system_name"].strip())
        dirm = re.fullmatch(r"Mast \d+([LR])[A-Z]?", name)
        if not (sw and fac and sysm and dirm):
            raise SystemExit(f"{DEVICE_MAP.name}: mast {name}: comment, notes, system name or name not as expected")
        mast_heads = re.findall(r"\((IH\d+)\)", sysm.group(3))
        missing = [h for h in mast_heads if h not in heads]
        if missing:
            raise SystemExit(f"{DEVICE_MAP.name}: mast {name}: heads {missing} have no head row")
        sys_name = f"IF$shsm:{sysm.group(1)}:{sysm.group(2)}" + "".join(f"({internal(h, name)})" for h in mast_heads)
        out_rows.append(dict(
            mast=name, cp=r["cp"], switch=sw.group(1), facing=fac.group(1),
            protects=f"OS Switch {sw.group(1)}", leg="", system_name=sys_name,
            head_system_names=";".join(f"{internal(h, name)}={heads[h]}" for h in mast_heads),
            device_system_name=r["system_name"].strip(), _level=int(r["level"])))
    pairs = {}
    for r in out_rows:
        pairs.setdefault((r["facing"], r["protects"]), []).append(r)
    for (facing, protects), group in pairs.items():
        if len(group) == 1:
            continue
        letters = {r["mast"][-1]: r for r in group}
        if len(group) != 2 or set(letters) != set(LEGS):
            raise SystemExit(f"masts {[r['mast'] for r in group]} share {facing} into {protects}: only an A and a B "
                             "mast can, on the switch's normal and diverging legs")
        for letter, r in letters.items():
            r["leg"] = LEGS[letter]
    if len({r["mast"] for r in out_rows}) != len(out_rows):
        raise SystemExit(f"{DEVICE_MAP.name}: a mast is named twice")
    out = io.StringIO()
    w = csv.DictWriter(out, level_masts.FIELDS, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for row in sorted(out_rows, key=lambda r: (r["_level"], int(re.search(r"\d+", r["mast"]).group()),
                                               r["mast"])):
        w.writerow(row)
    return out.getvalue()


def main(argv):
    if set(argv) - {"--check"}:
        print(__doc__)
        return 2
    text = build()
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(pd.REPO)} is out of date: run tools/schematic/build_main_upper_masts.py")
            return 1
        print("main_upper_masts.csv up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(pd.REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
