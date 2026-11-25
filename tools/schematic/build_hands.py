"""build_hands.py [--check]

Write the plan hands into jmri/layouts/hart/data/switches.csv: the hand (R or L, the diverging side seen from the
points) of every main and upper level switch half, read from the AnyRail plan graph (inputs/main.json, node `hand`
+1 = R, -1 = L) and renamed to the owner's switch numbers by the relabel edit in plan_overrides.json's main_upper
section. Switch 225 is the double crossover: it has no hand. These are plan hands (owner decision 2026-11-14), not
the schematic's drawn hands: 101A/B, 103A/B, 105, 107, 109 and 111 are flipped on the sheet. Provisional until the
Layout Editor import.

switches.csv is hand-kept, one row per OS block or switch half (switches.columns.csv). This script changes only the
`hand` cell of a main or upper row whose hand_source is `plan`, and the labels of a staging row's OS block and legs
(os_block, closed_leg, thrown_leg), which it sets to the name store's names of their device IDs (os_id, closed_id,
thrown_id; hartlib.devices.user_names), so a rename in devices_field.csv reaches switches.csv with no hand edit
(naming-layers step 5). A row whose hand_source is `owner` keeps its hand, and no row is added or removed. It stops, naming the row, on a plan label with no row (add
the row with hand_source plan and the hand blank: this fills it), a plan row the plan has no hand for, and a row of
a plan label with no hand_source.

--check regenerates in memory and exits 1 if the file differs.
"""
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS and hartlib paths
from hartlib import devices, railroad  # noqa: E402  the plan overrides and switches.csv, read and checked once

GRAPH = pd.GRAPHS / "main.json"
OVERRIDES = railroad.Sources.under().plan_overrides
OUT = railroad.Sources.under().switches

KNOWN_EDITS = {"relabel"}     # switch-changing edits this script reads; any other fails loudly


def plan_hands():
    """{label: "L" or "R"} of the plan graph, in the owner's labels. Fails on anything it cannot vouch for: an edit
    kind it does not read (a `switch`, `crossover` or `remove` edit changes which switches exist), a relabel key with
    no plan node other than the one double crossover, or a graph hand that is not +1 or -1."""
    nodes = json.loads(GRAPH.read_text())["nodes"]
    # the hands are a layer of their own: this reads the inputs only (railroad.LAYERS)
    rr = railroad.Railroad(railroad.Sources.under().but(plan_overrides=OVERRIDES), upto="inputs")
    try:
        edits, relabel = rr.plan_overrides.edits, rr.plan_overrides.relabel
    except railroad.FactsError as exc:
        raise SystemExit(f"build_hands.py: {exc}") from None
    unknown = sorted({e["op"] for e in edits} - KNOWN_EDITS)
    if unknown:
        raise SystemExit(f"build_hands.py does not read {unknown} edits yet: teach it before writing hands")
    by_label = {n["label"]: n for n in nodes.values() if n["kind"] == "switch"}
    by_label.update({i: n for i, n in nodes.items() if n["kind"] == "switch"})      # a switch the plan numbers no part for
    dx = {n["label"] for n in nodes.values() if n["kind"] == "dx"}
    out = {}
    for old, new in relabel.items():
        node = by_label.get(old)
        if node is None:
            if old in dx:
                continue                    # the double crossover: no hand
            raise SystemExit(f"relabel {old!r} -> {new!r}: no switch {old!r} in {GRAPH.name}")
        if node.get("hand") in (1, -1):
            out[new] = "R" if node["hand"] == 1 else "L"
        else:
            raise SystemExit(f"{old} ({new}): plan hand {node.get('hand')!r} is not +1 or -1")
    return out


def store_names(path):
    """The name store's {(level, id): user name} for switches.csv at `path`: the device master beside it (a test's
    copy), else the repo's. SystemExit on a master that does not load."""
    data = Path(path).parent
    try:
        return devices.user_names(devices.Files.under(data) if (data / devices.GENERATED_FILE).is_file() else None)
    except railroad.FactsError as exc:          # a DevicesError too (its subclass)
        raise SystemExit(f"build_hands.py: {exc}") from None


def apply(path, hands, names=None):
    """The text of switches.csv at `path` with the hand of each plan row set from `hands` ({label: hand}) and each
    staging row's os_block, closed_leg and thrown_leg the name of its os_id, closed_id and thrown_id in `names`
    (store_names by default); every other line as it was, byte for byte (a row already right too). Stops
    (SystemExit naming the file and line) on what the module text says, or an id the device master does not have."""
    name = path.name
    try:
        rows = railroad.read_switch_rows(path)
    except railroad.FactsError as exc:
        raise SystemExit(f"build_hands.py: {exc}") from None
    # by each row's key, not its level (naming-layers step 14): plan hands for the rows keyed by their half, the
    # labels for the rows keyed by their OS block's ID (railroad.SwitchRow.by_os)
    by_half = {r.half: r for r in rows if not r.by_os}
    bad = [f"{name}: plan switch {label} has no row; add one (level, switch, half {label}, hand_source plan, "
           "hand blank) and run build_hands.py"
           for label in sorted(set(hands) - set(by_half), key=railroad.natural)]
    for r in by_half.values():
        where = f"{name} line {r.line} ({r.half})"
        if r.hand_source == "plan" and r.half not in hands:
            bad.append(f"{where}: hand_source plan, but the plan has no hand for {r.half}")
        elif r.half in hands and not r.hand_source:
            bad.append(f"{where}: the plan has a hand for it ({hands[r.half]}); set hand_source plan or owner")
    if bad:
        raise SystemExit("build_hands.py:\n  " + "\n  ".join(bad))
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = next(csv.reader(lines[:1]))
    col, half_col = header.index("hand"), header.index("half")
    staging = [r for r in rows if r.by_os]
    if staging:
        names = store_names(path) if names is None else names
    for r in staging:                   # the labels: the name store's names of the row's IDs
        cells = next(csv.reader(lines[r.line - 1:r.line]))
        changed = False
        for label, ident in railroad.LEG_IDS.items():
            want = names.get((str(r.level), getattr(r, ident)))
            if want is None:
                bad.append(f"{name} line {r.line}: {ident} {getattr(r, ident)} is no level {r.level} device of the "
                           "device master (a new export dropped it: give the row the device's new id)")
                continue
            i = header.index(label)
            if cells[i] != want:
                cells[i], changed = want, True
        if changed:
            out = io.StringIO()
            csv.writer(out, lineterminator="\n").writerow(cells)
            lines[r.line - 1] = out.getvalue()
    if bad:
        raise SystemExit("build_hands.py:\n  " + "\n  ".join(bad))
    for r in by_half.values():
        if r.hand_source != "plan" or r.hand == hands[r.half]:
            continue
        # read_rows counts lines as the csv reader does; no cell of switches.csv holds a line break, so row N is line N
        cells = next(csv.reader(lines[r.line - 1:r.line]))
        if (cells[col].strip(), cells[half_col].strip()) != (r.hand, r.half):        # the reader strips values
            raise SystemExit(f"build_hands.py: {name} line {r.line}: cannot find the row of {r.half} on its line")
        cells[col] = hands[r.half]
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerow(cells)
        lines[r.line - 1] = out.getvalue()
    return "".join(lines)


def build():
    """switches.csv's text with the plan hands written in."""
    return apply(OUT, plan_hands())


def main(argv):
    if set(argv) - {"--check"}:
        print(__doc__)
        return 2
    text = build()
    if "--check" in argv:
        if OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(pd.REPO)}: its plan hands or staging labels are out of date: run "
                  "tools/schematic/build_hands.py")
            return 1
        print("switches.csv plan hands up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(pd.REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
