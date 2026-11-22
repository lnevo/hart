#!/usr/bin/env python3
"""Write www/behind/layout-docs.html, the layout documentation, from its template and block_lengths.csv.

The page began as the Model Railroad Engineer SOQ (docs/ap/electrical) without the NMRA form, the
checklist, the requirement framing and the wiring-record appendix (owner, 2026-11-22). It no longer
reads anything from the SOQ, which was submitted and is frozen; the page is maintained on its own
(owner, 2026-11-22). Its text is layout_docs_template.html, and its drawings and photos are files
under www/assets/behind/layout-docs/, edited in place. This script fills in the list of detected
sections from jmri/layouts/hart/data/block_lengths.csv and checks that drawing D2 states the same
count.

    python3 www/scripts/build_layout_docs.py           # write the page
    python3 www/scripts/build_layout_docs.py --check   # exit 1 if the page is out of date
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import sys
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
ROOT = PORTAL.parent
BLOCKS = ROOT / "jmri/layouts/hart/data/block_lengths.csv"
TEMPLATE = PORTAL / "scripts/layout_docs_template.html"
PAGE = PORTAL / "behind/layout-docs.html"
DRAWINGS = PORTAL / "assets/behind/layout-docs/drawings"
D2 = DRAWINGS / "D2-propulsion-sections.svg"
# SOQ wording that must not come back into the page's drawings (they began as SOQ copies).
SOQ_WORDS = ("Section 3.", "Section 4.", "Section 5.", "Appendix", "SOQ", "my own", "by me", "witness", "evaluator",
             "Requirement", "claim")

# Labels used on the page for the layout's section names (the overview's label table).
YARD = {"S-R": "Y1", "S-1": "Y2", "S-2": "Y3", "S-3": "Y4", "S-4": "Y5"}
FIXED = {"Main West": "Main line (west), RS-1", "West Ext": "Double-track section", "East Lead": "Double-track section",
         "Brick-Plane": "Main line (east)", "East Ext": "Main line beside the passing siding", "Main East": "Main line (east)",
         "K-1": "Return loop RS-2", "K-2": "Return loop RS-2", "Scale": "Passing siding", "Barn": "Yard lead",
         "W-1": "Holding track", "W-2": "Holding track"}


# label() began as a copy of the frozen docs/ap/electrical/build_soq.py generic() (2026-11-22); this is
# the maintained one. Add a new section name here, not there.
def label(name: str) -> str:
    """The page's description of a detected section, from its layout name."""
    if name in YARD:
        return f"Yard track {YARD[name]}"
    m = re.fullmatch(r"EH-(\d)", name)
    if m:
        return f"Engine storage E{m.group(1)}"
    if name in FIXED:
        return FIXED[name]
    m = re.fullmatch(r"OS Switch (\d+)([ab]?)", name)
    if m:
        n, half = m.groups()
        return f"Turnout {n}{' (crossover half ' + half + ')' if half else ''}"
    raise SystemExit(f"build_layout_docs: no label for section {name!r}; add it to label()")


def detected_sections() -> list[dict]:
    """One row per detector ("Block n-c"), by node and channel. A short piece that shares its OS
    block's detector ("a part of OS Switch 1" in the note) is folded into that row. The length is
    the measured one when the detector was timed (it covers the whole detector), else the plan
    lengths added up, marked as an estimate."""
    with BLOCKS.open() as f:
        rows = list(csv.DictReader(f))
    by_sensor: dict[str, dict] = {}
    for r in rows:
        m = re.fullmatch(r"Block (\d+)-(\d+)", r["occupancy_sensor"])
        if not m:
            continue
        whole = re.search(r"a part of (.+?),", r["note"])
        part = bool(whole)
        s = by_sensor.setdefault(r["occupancy_sensor"], {"node": int(m.group(1)), "ch": int(m.group(2)),
                                                         "name": None, "plan": 0.0, "measured": None})
        s["plan"] += float(r["plan_in"])
        if not part:
            if s["name"]:
                raise SystemExit(f"build_layout_docs: {r['occupancy_sensor']} has two sections, {s['name']} and {r['user_name']}")
            s["name"] = r["user_name"].replace("Track ", "")
            if r["source"] == "timed":
                s["measured"] = float(r["measured_in"])
        if part:
            s.setdefault("parts", []).append((r["user_name"], whole.group(1)))
    out = []
    for sensor, s in by_sensor.items():
        for piece, owner in s.get("parts", []):
            if owner != s["name"]:
                raise SystemExit(f"build_layout_docs: {piece} is noted as a part of {owner} but is on {sensor}, {s['name']}'s detector")
        if not s["name"]:
            raise SystemExit(f"build_layout_docs: {sensor} has only parts, no section of its own")
        timed = s["measured"] is not None
        out.append({"name": s["name"], "node": s["node"], "ch": s["ch"], "estimate": not timed,
                    "inches": s["measured"] if timed else s["plan"]})
    return sorted(out, key=lambda s: (s["node"], s["ch"]))


def sections_table() -> tuple[str, int]:
    rows = detected_sections()
    body = "".join(
        f"<tr><td class=\"num\">{i}</td><td>{html.escape(label(s['name']))}</td>"
        f"<td>{html.escape(s['name'])}</td><td>C{s['node']} · {s['ch']}</td>"
        f"<td class=\"num\">{'≈ ' if s['estimate'] else ''}{s['inches']:.0f}</td></tr>"
        for i, s in enumerate(rows, 1))
    table = ('<div class="table-wrap">\n        <table class="data-table" id="tab-sections">\n'
             '          <thead><tr><th scope="col">No.</th><th scope="col">Section</th><th scope="col">Layout name</th>'
             '<th scope="col">Node · ch</th><th scope="col">Length, in</th></tr></thead>\n'
             f'          <tbody>{body}</tbody>\n        </table>\n      </div>')
    return table, len(rows)


def check_d2(count: int) -> None:
    """Drawing D2 says how many sections are wired its way; it must match the section list."""
    if not D2.is_file():
        raise SystemExit(f"build_layout_docs: {D2.relative_to(ROOT)} is missing; the section count check reads it")
    said = re.search(r"All (\d+) detected sections", D2.read_text())
    if not said or int(said.group(1)) != count:
        raise SystemExit(f"build_layout_docs: {D2.relative_to(ROOT)} says {said.group(1) if said else 'no'} detected "
                         f"sections, block_lengths.csv has {count}; edit the drawing")


def check_drawings() -> None:
    """No SOQ wording in the visible text of the page's drawings."""
    for svg in sorted(DRAWINGS.glob("*.svg")):
        text = " ".join(re.findall(r"<(?:text|tspan|title|desc)\b[^>]*>([^<]*)", svg.read_text()))
        for word in SOQ_WORDS:
            if word in text:
                raise SystemExit(f"build_layout_docs: {svg.relative_to(ROOT)} says {word!r}, SOQ wording; edit the drawing")


def outputs() -> dict[Path, str]:
    table, count = sections_table()
    page = TEMPLATE.read_text().replace("{{SECTIONS_TABLE}}", table).replace("{{SECTION_COUNT}}", str(count))
    if "{{" in page:
        raise SystemExit("build_layout_docs: a placeholder is left in the page")
    check_d2(count)
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
