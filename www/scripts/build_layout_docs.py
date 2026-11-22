#!/usr/bin/env python3
"""Write www/behind/layout-docs.html, the layout documentation, from the SOQ's drawings and data.

The page is the Model Railroad Engineer SOQ (docs/ap/electrical) without the NMRA form, the
checklist, the requirement framing and the wiring-record appendix (owner, 2026-11-22). Its text
is layout_docs_template.html; this script fills in the list of detected sections from
jmri/layouts/hart/data/block_lengths.csv and writes copies of the SOQ drawings with the SOQ's
section and appendix references taken out. The SOQ itself is frozen and is not touched. Photos
are served from docs/ap/electrical/photos through published-files.json.

    python3 www/scripts/build_layout_docs.py           # write the page and drawings
    python3 www/scripts/build_layout_docs.py --check   # exit 1 if either is out of date
"""
from __future__ import annotations

import argparse
import csv
import html
import importlib.util
import re
import sys
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
ROOT = PORTAL.parent
SOQ = ROOT / "docs/ap/electrical"
BLOCKS = ROOT / "jmri/layouts/hart/data/block_lengths.csv"
TEMPLATE = PORTAL / "scripts/layout_docs_template.html"
PAGE = PORTAL / "behind/layout-docs.html"
DRAWINGS_OUT = PORTAL / "assets/behind/layout-docs/drawings"
DRAWINGS = ["D1-propulsion-one-line", "D2-propulsion-sections", "D3-turnout-frog-indication", "D4-crossover",
            "D5-reversing-section", "D6-computer-interface", "P0-staging-to-scale", "P1-staging-plan",
            "P2-reversing-sections", "P3-passing-siding", "P4-yard", "P5-engine-storage"]

# Text in the SOQ drawings that points into the SOQ: (drawing, old, new). Each must be found.
FIXES = [
    ("D2-propulsion-sections", "are wired this way; Appendix B lists them.", "are wired this way."),
    ("D2-propulsion-sections", "All 43 detected sections", "All {count} detected sections"),
    ("D3-turnout-frog-indication", " (Section 5.1).", "."),
    ("D6-computer-interface", "my own work", "built for HART"),
    ("D6-computer-interface", "were designed and written by me and are", "were designed and written for HART and are"),
    ("D6-computer-interface", "bridge node firmware were written by me.", "bridge node firmware were written for HART."),
    ("P2-reversing-sections", "(positions schematic; the witness sees the real gaps)", "(positions schematic)"),
    ("P1-staging-plan", " (Section 3.3)", ""),
    ("P1-staging-plan", " (Section 3.4)", ""),
    ("P1-staging-plan", " (Section 3.6)", ""),
    ("P1-staging-plan", " (Sections 3.5 and 3.6)", ""),
]
LEFTOVER = ("Section 3.", "Section 5.", "Appendix", "SOQ", "my own", "by me", "witness", "evaluator")


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


def _build_soq():
    """The frozen SOQ builder, loaded from its file so docs/ap/electrical never goes on sys.path."""
    spec = importlib.util.spec_from_file_location("build_soq", SOQ / "build_soq.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sections_table() -> tuple[str, int]:
    build_soq = _build_soq()
    rows = detected_sections()
    body = "".join(
        f"<tr><td class=\"num\">{i}</td><td>{html.escape(build_soq.generic(s['name']))}</td>"
        f"<td>{html.escape(s['name'])}</td><td>C{s['node']} · {s['ch']}</td>"
        f"<td class=\"num\">{'≈ ' if s['estimate'] else ''}{s['inches']:.0f}</td></tr>"
        for i, s in enumerate(rows, 1))
    table = ('<div class="table-wrap">\n        <table class="data-table" id="tab-sections">\n'
             '          <thead><tr><th scope="col">No.</th><th scope="col">Section</th><th scope="col">Layout name</th>'
             '<th scope="col">Node · ch</th><th scope="col">Length, in</th></tr></thead>\n'
             f'          <tbody>{body}</tbody>\n        </table>\n      </div>')
    return table, len(rows)


def drawing(name: str, count: int) -> str:
    svg = (SOQ / "drawings" / f"{name}.svg").read_text()
    for d, old, new in FIXES:
        if d != name:
            continue
        if old not in svg:
            raise SystemExit(f"build_layout_docs: {name}.svg no longer has {old!r}; update FIXES")
        svg = svg.replace(old, new.format(count=count))
    text = " ".join(re.findall(r"<(?:text|tspan|title|desc)\b[^>]*>([^<]*)", svg))
    for word in LEFTOVER:
        if word in text:
            raise SystemExit(f"build_layout_docs: {name}.svg still says {word!r}; add it to FIXES")
    return svg


def outputs() -> dict[Path, str]:
    table, count = sections_table()
    page = TEMPLATE.read_text().replace("{{SECTIONS_TABLE}}", table).replace("{{SECTION_COUNT}}", str(count))
    if "{{" in page:
        raise SystemExit("build_layout_docs: a placeholder is left in the page")
    out = {PAGE: page}
    out.update({DRAWINGS_OUT / f"{n}.svg": drawing(n, count) for n in DRAWINGS})
    return out


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
