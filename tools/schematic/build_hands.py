"""build_hands.py [--check]

Write the plan hands into jmri/layouts/hart/data/switches.csv: the hand (R or L, the diverging side seen from the
points) of every main and upper level switch half, read from the AnyRail plan graph (inputs/main.json, node `hand`
+1 = R, -1 = L) and renamed to the owner's switch numbers by the relabel edit in plan_overrides.json's main_upper
section. Switch 225 is the double crossover: it has no hand. These are plan hands (owner decision 2026-11-14), not
the schematic's drawn hands: 101A/B, 103A/B, 105, 107, 109 and 111 are flipped on the sheet. Provisional until the
Layout Editor import.

switches.csv is hand-kept, one row per OS block or switch half (switches.columns.csv). This script changes only the
`hand` cell of a main or upper row whose hand_source is `plan`. A staging row gives its OS block and legs by device
ID only; their names are the name store's, which hartlib.railroad_facts.read_switch_rows looks up, so nothing here
writes a name. A row whose hand_source is `owner` keeps its hand, and no row is added or removed. It stops, naming the
row, on a plan label with no row (add the row with hand_source plan and the hand blank: this fills it), a plan row
the plan has no hand for, and a row of a plan label with no hand_source.

--check regenerates in memory and exits 1 if the file differs.
"""
import csv
import io
import json
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS and hartlib paths
from hartlib import railroad  # noqa: E402  the plan overrides and switches.csv, read and checked once

GRAPH = pd.GRAPHS / "main.json"
OVERRIDES = railroad.Sources.under().plan_overrides
OUT = railroad.Sources.under().switches

KNOWN_EDITS = {"relabel"}     # switch-changing edits this script reads; any other fails loudly


class HandsError(Exception):
    """The plan or switches.csv holds something the hands cannot be written from; the message names the file and
    row. main() prints it and exits 1."""


def plan_hands() -> dict[str, str]:
    """{label: "L" or "R"} of the plan graph, in the owner's labels. HandsError on anything it cannot vouch for: an
    edit kind it does not read (a `switch`, `crossover` or `remove` edit changes which switches exist), a relabel key
    with no plan node other than the one double crossover, or a graph hand that is not +1 or -1."""
    nodes = json.loads(GRAPH.read_text())["nodes"]
    # the hands are a layer of their own: this reads the inputs only (railroad.LAYERS)
    rr = railroad.Railroad(railroad.Sources.under().but(plan_overrides=OVERRIDES), upto="inputs")
    try:
        edits, relabel = rr.plan_overrides.edits, rr.plan_overrides.relabel
    except railroad.FactsError as exc:
        raise HandsError(f"build_hands.py: {exc}") from exc
    unknown = sorted({e["op"] for e in edits} - KNOWN_EDITS)
    if unknown:
        raise HandsError(f"build_hands.py does not read {unknown} edits yet: teach it before writing hands")
    by_label = {n["label"]: n for n in nodes.values() if n["kind"] == "switch"}
    by_label.update({i: n for i, n in nodes.items() if n["kind"] == "switch"})      # a switch the plan numbers no part for
    dx = {n["label"] for n in nodes.values() if n["kind"] == "dx"}
    out: dict[str, str] = {}
    for old, new in relabel.items():
        node = by_label.get(old)
        if node is None:
            if old in dx:
                continue                    # the double crossover: no hand
            raise HandsError(f"relabel {old!r} -> {new!r}: no switch {old!r} in {GRAPH.name}")
        if node.get("hand") in (1, -1):
            out[new] = "R" if node["hand"] == 1 else "L"
        else:
            raise HandsError(f"{old} ({new}): plan hand {node.get('hand')!r} is not +1 or -1")
    return out


def apply(path: Path, hands: Mapping[str, str], names: Mapping[tuple[str, str], str] | None = None) -> str:
    """The text of switches.csv at `path` with the hand of each plan row set from `hands` ({label: hand}); every other
    line as it was, byte for byte (a row already right too). `names`: the name store the read checks the staging rows'
    IDs against (railroad.read_switch_rows; the device master beside `path`, else the repo's, by default).
    HandsError, naming the file and line, on what the module text says, or a row read_switch_rows refuses."""
    name = path.name
    try:
        rows = railroad.read_switch_rows(path, names)
    except railroad.FactsError as exc:
        raise HandsError(f"build_hands.py: {exc}") from exc
    # by each row's key, not its level: plan hands for the rows keyed by their half
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
        raise HandsError("build_hands.py:\n  " + "\n  ".join(bad))
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = next(csv.reader(lines[:1]))
    col, half_col = header.index("hand"), header.index("half")
    for r in by_half.values():
        if r.hand_source != "plan" or r.hand == hands[r.half]:
            continue
        # read_rows counts lines as the csv reader does; no cell of switches.csv holds a line break, so row N is line N
        cells = next(csv.reader(lines[r.line - 1:r.line]))
        if (cells[col].strip(), cells[half_col].strip()) != (r.hand, r.half):        # the reader strips values
            raise HandsError(f"build_hands.py: {name} line {r.line}: cannot find the row of {r.half} on its line")
        cells[col] = hands[r.half]
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerow(cells)
        lines[r.line - 1] = out.getvalue()
    return "".join(lines)


def build() -> str:
    """switches.csv's text with the plan hands written in (HandsError as plan_hands and apply raise it)."""
    return apply(OUT, plan_hands())


def main(argv: list[str]) -> int:
    if set(argv) - {"--check"}:
        print(__doc__)
        return 2
    try:
        text = build()
    except HandsError as exc:
        sys.exit(str(exc))
    if "--check" in argv:
        if OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(pd.REPO)}: its plan hands are out of date: run "
                  "tools/schematic/build_hands.py")
            return 1
        print("switches.csv plan hands up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(pd.REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
