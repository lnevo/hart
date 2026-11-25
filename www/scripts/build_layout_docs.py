#!/usr/bin/env python3
"""Write www/behind/layout-docs.html, the layout documentation, from its template, block_lengths.csv and the device master.

The page began as the Model Railroad Engineer SOQ (docs/ap/electrical) without the NMRA form, the
checklist, the requirement framing and the wiring-record appendix (owner, 2026-11-22). It reads nothing
from the SOQ, which was submitted and is frozen; the page is a live document that follows the layout's data
(owner, 2026-11-25). Its text is layout_docs_template.html, and its drawings and photos are files under
www/assets/behind/layout-docs/, edited in place. This script fills in the list of detected sections (lengths
and detectors from jmri/layouts/hart/data/block_lengths.csv by level and ID, names from the device master,
where the owner's name wins), the track names the template gives by block ID ({{name:<id>}}) and the
figures its text states (section count, RS-1, siding and yard lengths, the crossovers), and checks that
drawing D2 states the same count and plans P3 and P4 the same lengths.

    python3 www/scripts/build_layout_docs.py           # write the page
    python3 www/scripts/build_layout_docs.py --check   # exit 1 if the page is out of date
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, railroad  # noqa: E402

PORTAL = Path(__file__).resolve().parents[1]
ROOT = PORTAL.parent
TEMPLATE = PORTAL / "scripts/layout_docs_template.html"
PAGE = PORTAL / "behind/layout-docs.html"
DRAWINGS = PORTAL / "assets/behind/layout-docs/drawings"
D2 = DRAWINGS / "D2-propulsion-sections.svg"
P3 = DRAWINGS / "P3-passing-siding.svg"
P4 = DRAWINGS / "P4-yard.svg"
# SOQ wording that must not come back into the page's drawings (they began as SOQ copies).
SOQ_WORDS = ("Section 3.", "Section 4.", "Section 5.", "Appendix", "SOQ", "my own", "by me", "witness", "evaluator",
             "Requirement", "claim")
LEVEL = "1"          # the template's {{name:...}} blocks are on the staging level

# The page's labels for the layout's sections, by block ID (naming-layers step 5: a rename in devices_field.csv keeps
# the ID, so the label stays and the name beside it follows). A new section needs its label here; a switch
# renumbered in the plan changes its blocks' IDs, and the build stops on the old ones.
YARD = ("block:15B-23B", "block:17C-29C", "block:19C-27C", "block:21C-25C", "block:21B-25B")     # Y1 to Y5
ENGINE = ("block:11B-end", "block:9B-end", "block:9C-end")                                      # E1 to E3
RS1, SIDING = "block:1A-23A", "block:5C-7B"
LABELS = {
    **{bid: f"Yard track Y{n}" for n, bid in enumerate(YARD, 1)},
    **{bid: f"Engine storage E{n}" for n, bid in enumerate(ENGINE, 1)},
    RS1: "Main line (west), RS-1", "block:23B-35B": "Double-track section", "block:33A-35A": "Double-track section",
    "block:1C-5A#1+1C-5A#2": "Main line (east)", "block:5B-7A": "Main line beside the passing siding",
    "block:7B-33C": "Main line (east)", "block:37C-39C#2": "Return loop RS-2", "block:37C-39C#1": "Return loop RS-2",
    SIDING: "Passing siding", "block:7A-13C": "Yard lead", "block:3B-end": "Holding track",
    "block:3C-end": "Holding track"}
CAR_IN = 7.5         # the page's car length, for the siding's "about n cars" (the SOQ's 144 in held about 19)
NAME = re.compile(r"\{\{name:([^}]+)\}\}")     # {{name:<block id>}}: the store's name of a staging block, "S-1"
OS = re.compile(r"os:(\d+)(:.+)?")             # an OS block's ID: its switch number, and a leg on a crossover half
# What plans P3 and P4 (hand-edited files) must say: the page's figures.
PLAN_TEXT = {P3: "Passing siding, {SIDING_IN} in long (about {SIDING_CARS} cars)",
             P4: "Yard tracks Y1 to Y5, {YARD_IN} in long"}


def bare(name: str) -> str:
    """A track's name as the page shows it: "S-1" for "Track S-1"; an OS block's in full."""
    return name.removeprefix("Track ")


def label(section: dict) -> str:
    """The page's description of a detected section, by its block ID."""
    if section["id"] in LABELS:
        return LABELS[section["id"]]
    m = OS.fullmatch(section["id"])
    if m:
        half = re.search(r"([ab])$", section["name"]) if m.group(2) else None
        return f"Turnout {m.group(1)}{' (crossover half ' + half.group(1) + ')' if half else ''}"
    raise SystemExit(f"build_layout_docs: no label for section {section['id']} ({section['name']}); add it to LABELS")


def master_rows(files=None) -> dict[tuple[str, str], dict]:
    """{(level, id): merged device-master row} (hartlib.devices.load: the owner's name wins). `files` a test's copy."""
    return {(r["level"], r["id"]): r for r in devices.load(files) if r["level"] and r["id"]}


def detected_sections(lengths=None, master=None) -> list[dict]:
    """One row per detector ("Block n-c"), by node and channel. Lengths and detectors come from block_lengths.csv
    (by level and ID), names from the device master, so a rename in the field file reaches the page with no build
    step between. A part (role part: a short piece on its OS block's detector) is folded into its block's row. The
    length is the measured one when the detector was timed (it covers the whole detector), else the plan lengths
    added up, marked as an estimate."""
    lengths = railroad.read_block_lengths() if lengths is None else lengths      # this checkout's file, in file order
    master = master_rows() if master is None else master
    by_sensor: dict[str, dict] = {}
    for b in lengths.values():
        m = re.fullmatch(r"Block (\d+)-(\d+)", b.occupancy_sensor)
        if not m:
            continue
        row = master.get((b.level, b.id))
        if row is None:
            raise SystemExit(f"build_layout_docs: block_lengths.csv line {b.line}: {b.id} is no level {b.level} "
                             "device of the device master")
        s = by_sensor.setdefault(b.occupancy_sensor, {"node": int(m.group(1)), "ch": int(m.group(2)), "id": None,
                                                      "name": None, "plan": 0.0, "measured": None})
        s["plan"] += b.plan_in
        if row["role"] == "part":
            s.setdefault("parts", []).append((row["user_name"], row["part_of"]))
            continue
        if s["id"]:
            raise SystemExit(f"build_layout_docs: {b.occupancy_sensor} has two sections, {s['name']} and "
                             f"{row['user_name']}")
        s["id"], s["name"] = b.id, row["user_name"]
        if b.source == "timed":
            s["measured"] = b.measured_in
    out = []
    for sensor, s in by_sensor.items():
        if not s["id"]:
            raise SystemExit(f"build_layout_docs: {sensor} has only parts, no section of its own")
        for piece, owner in s.get("parts", []):
            if owner != s["name"]:
                raise SystemExit(f"build_layout_docs: {piece} is a part of {owner} but is on {sensor}, "
                                 f"{s['name']}'s detector")
        timed = s["measured"] is not None
        out.append({"id": s["id"], "name": bare(s["name"]), "node": s["node"], "ch": s["ch"], "estimate": not timed,
                    "inches": s["measured"] if timed else s["plan"]})
    return sorted(out, key=lambda s: (s["node"], s["ch"]))


def sections_table(rows: list[dict]) -> str:
    body = "".join(
        f"<tr><td class=\"num\">{i}</td><td>{html.escape(label(s))}</td>"
        f"<td>{html.escape(s['name'])}</td><td>C{s['node']} · {s['ch']}</td>"
        f"<td class=\"num\">{'≈ ' if s['estimate'] else ''}{s['inches']:.0f}</td></tr>"
        for i, s in enumerate(rows, 1))
    return ('<div class="table-wrap">\n        <table class="data-table" id="tab-sections">\n'
            '          <thead><tr><th scope="col">No.</th><th scope="col">Section</th><th scope="col">Layout name</th>'
            '<th scope="col">Node · ch</th><th scope="col">Length, in</th></tr></thead>\n'
            f'          <tbody>{body}</tbody>\n        </table>\n      </div>')


def facts(rows: list[dict]) -> dict[str, str]:
    """The figures the page's text states, from the section list and rounded as it shows them. A length from plan
    estimates (marked ≈ in the list) is said as "about"."""
    inches = {s["id"]: float(f"{s['inches']:.0f}") for s in rows}
    estimate = {s["id"]: s["estimate"] for s in rows}
    named = {"RS1": [RS1], "SIDING": [SIDING], "YARD": list(YARD)}
    missing = [f"{entry} {bid}" for entry, ids in named.items() for bid in ids if bid not in inches]
    if missing:
        raise SystemExit(f"build_layout_docs: no detected section for {', '.join(missing)}; the page states its "
                         "length (fix the entry in build_layout_docs.py)")

    def about(ids) -> str:
        return "about " if any(estimate[bid] for bid in ids) else ""
    yard = sorted(inches[bid] for bid in YARD)
    xings = sorted({int(m.group(1)) for s in rows if (m := OS.fullmatch(s["id"])) and m.group(2)})
    if not xings:
        raise SystemExit("build_layout_docs: no crossover half in the section list; the page names the crossovers")
    listed = " and ".join(filter(None, [", ".join(map(str, xings[:-1])), str(xings[-1])]))
    return {"SECTION_COUNT": str(len(rows)), "RS1_IN": f"{about([RS1])}{inches[RS1]:.0f}",
            "SIDING_IN": f"{about([SIDING])}{inches[SIDING]:.0f}", "SIDING_CARS": str(round(inches[SIDING] / CAR_IN)),
            "YARD_IN": f"{about(YARD)}{yard[0]:.0f} to {yard[-1]:.0f}",
            "CROSSOVERS": (f"crossovers at Switches {listed}" if len(xings) > 1 else f"a crossover at Switch {listed}")}


def fill_names(text: str, master: dict) -> str:
    """Each {{name:<block id>}} in `text` replaced by the store's name of that staging block."""
    def one(m: re.Match) -> str:
        row = master.get((LEVEL, m.group(1)))
        if row is None:
            raise SystemExit(f"build_layout_docs: the template names {m.group(1)}, no level {LEVEL} device of the "
                             "device master")
        return html.escape(bare(row["user_name"]))
    return NAME.sub(one, text)


def check_d2(count: int) -> None:
    """Drawing D2 says how many sections are wired its way; it must match the section list."""
    if not D2.is_file():
        raise SystemExit(f"build_layout_docs: {D2.relative_to(ROOT)} is missing; the section count check reads it")
    said = re.search(r"All (\d+) detected sections", D2.read_text())
    if not said or int(said.group(1)) != count:
        raise SystemExit(f"build_layout_docs: {D2.relative_to(ROOT)} says {said.group(1) if said else 'no'} detected "
                         f"sections, block_lengths.csv has {count}; edit the drawing")


def check_plans(fact: dict[str, str]) -> None:
    """Plans P3 and P4 state the siding's and the yard's lengths; they must be the page's."""
    for svg, text in PLAN_TEXT.items():
        want = text.format(**fact)
        if want not in svg.read_text():
            raise SystemExit(f"build_layout_docs: {svg.relative_to(ROOT)} must say {want!r}, as the section list "
                             "does; edit the drawing")


def check_drawings() -> None:
    """No SOQ wording in the visible text of the page's drawings."""
    for svg in sorted(DRAWINGS.glob("*.svg")):
        text = " ".join(re.findall(r"<(?:text|tspan|title|desc)\b[^>]*>([^<]*)", svg.read_text()))
        for word in SOQ_WORDS:
            if word in text:
                raise SystemExit(f"build_layout_docs: {svg.relative_to(ROOT)} says {word!r}, SOQ wording; edit the drawing")


def outputs(files=None) -> dict[Path, str]:
    """The page. `files` is the device master's (hartlib.devices.Files of a test's copy); None the repo's."""
    master = master_rows(files)
    rows = detected_sections(master=master)
    fact = facts(rows)
    page = fill_names(TEMPLATE.read_text(), master).replace("{{SECTIONS_TABLE}}", sections_table(rows))
    for key, value in fact.items():
        page = page.replace("{{" + key + "}}", value)
    if "{{" in page:
        raise SystemExit("build_layout_docs: a placeholder is left in the page")
    check_d2(len(rows))
    check_plans(fact)
    check_drawings()
    return {PAGE: page}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="report stale outputs and exit 1, write nothing")
    a = ap.parse_args()
    stale = []
    for path, text in outputs().items():
        if path.exists() and path.read_text() == text:
            continue
        stale.append(path.relative_to(ROOT))
        if not a.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if a.check and stale:
        print("build_layout_docs: out of date, run www/scripts/build_layout_docs.py:\n  " +
              "\n  ".join(map(str, stale)))
        return 1
    print(f"build_layout_docs: {'wrote ' + str(len(stale)) + ' file(s)' if stale else 'up to date'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
