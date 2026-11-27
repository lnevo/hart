#!/usr/bin/env python3
"""Write www/behind/layout-docs.html, the layout documentation, from its template and the layout's data.

The page began as the Model Railroad Engineer SOQ (docs/ap/electrical) without the NMRA form, the
checklist, the requirement framing and the wiring-record appendix. It reads nothing from the SOQ, which was
submitted and is frozen; the page is a live document that follows the layout's data. Its text is layout_docs_template.html, and its drawings and photos are files under
www/assets/behind/layout-docs/, edited in place. This script fills in the list of detected sections (lengths
and detectors from jmri/layouts/hart/data/block_lengths.csv by level and ID, names from the device master,
where the owner's name wins), the track names the template gives by block ID ({{name:<id>}}), the switch names
and DCC addresses it gives by turnout ID ({{turnout:switch:3}}, {{turnouts:switch:9,switch:11}}, {{dcc:switch:3}}),
the station names it gives by a switch of the station ({{station:switch:5}}: stations.csv's level 1 station holding
that switch, the smallest when two do) and the figures its text states (section count, RS-1, siding and yard
lengths, the siding's 50 ft cars at the plan's scale, the crossovers), and checks that drawing D2 states the same
count, plans P3 and P4 the same lengths, the plans' switch labels the live switch numbers and the drawings' station
labels (data-station) the names stations.csv gives.

    python3 www/scripts/build_layout_docs.py           # write the page
    python3 www/scripts/build_layout_docs.py --check   # exit 1 if the page is out of date
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import block_lengths, devices, layer_files, railroad  # noqa: E402
from hartlib.railroad_facts import DeviceRow  # noqa: E402

class LayoutDocsError(Exception):
    """The page's sources disagree with each other or with the template; the message names the file and the fix."""


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
Master = dict[tuple[str, str], DeviceRow]      # master_rows: {(level cell, id): row}

# The page's labels for the layout's sections, by block ID (naming-layers step 5: a rename in devices_field.csv keeps
# the ID, so the label stays and the name beside it follows). A new section needs its label here; a switch
# renumbered in the plan changes its blocks' IDs, and the build stops on the old ones.
YARD = ("block:15B-23B", "block:17C-29C", "block:19C-27C", "block:21C-25C", "block:21B-25B")     # Y1 to Y5
ENGINE = ("block:11B-end", "block:9B-end", "block:9C-end")                                      # E1 to E3
RS1, SIDING = "block:1A-23A", "block:5C-7B"
PLANS = sorted(DRAWINGS.glob("P*.svg"))    # the plans, each labelled with every staging switch number
# A switch label on the plans: "Sw <n>" on P0; on P1 to P5 a number in the labels' bold grey, which no other number has
P0_LABEL = re.compile(r"Sw (\d+)")
LABEL_STYLE = ('font-weight="bold"', 'fill="#5f6e7a"')
# A station's name in a drawing is a <text data-station="switch:<n>"> label (its text may sit in <tspan>s), which must
# hold the station that {{station:switch:<n>}} gives (stations.csv, through hartlib.railroad); an untagged element
# whose whole text is a station's name, in any case, stops the build. A name inside a longer label is not a station's.
SVG_TEXT = re.compile(r"<(text|tspan|title|desc)\b([^>]*)>(.*?)</\1>", re.S)
TSPAN = re.compile(r"<tspan\b[^>]*>(.*?)</tspan>", re.S)    # a line of a <text>, checked on its own too
DATA_STATION = re.compile(r'\bdata-station="([^"]*)"')
LABELS = {
    **{bid: f"Yard track Y{n}" for n, bid in enumerate(YARD, 1)},
    **{bid: f"Engine storage E{n}" for n, bid in enumerate(ENGINE, 1)},
    RS1: "Main line (west), RS-1", "block:23B-35B": "Double-track section", "block:33A-35A": "Double-track section",
    "block:1C-5A#1+1C-5A#2": "Main line (east)", "block:5B-7A": "Main line beside the passing siding",
    "block:7B-33C": "Main line (east)", "block:37C-39C#2": "Return loop RS-2", "block:37C-39C#1": "Return loop RS-2",
    SIDING: "Passing siding", "block:7A-13C": "Yard lead", "block:3B-end": "Holding track",
    "block:3C-end": "Holding track"}
# The siding's "about n 50 ft cars". A 50 ft car is 50 scale ft over the body, about 6.9 in at
# 1:87.1; with 5 scale ft added for the couplers and the gap between cars (about 55 ft coupler face to coupler face),
# each car takes about 7.6 in of track. The scale is the plan's (plan_overrides.json, staging scale_ratio).
CAR_FT, COUPLER_FT = 50, 5
NAME = re.compile(r"\{\{name:([^}]+)\}\}")     # {{name:<block id>}}: the store's name of a staging block, "S-1"
OS = re.compile(r"os:(\d+)(:.+)?")             # an OS block's ID: its switch number, and a leg on a crossover half
# {{turnout:<id>}} a turnout's name ("Switch 3"), {{turnouts:<id>,<id>}} several ("Switches 9 and 11"), {{dcc:<id>}} its
# DCC address, {{station:<switch id>}} the station at that switch; each ID a staging turnout's (switch:<n>)
SWITCHES = re.compile(r"\{\{(turnouts?|dcc|station):([^}]+)\}\}")
SWITCH_NAME = re.compile(r"Switch (\d+)")      # a turnout's name, whose number the plans print
# What plans P3 and P4 (hand-edited files) must say: the page's figures.
PLAN_TEXT = {P3: "Passing siding, {SIDING_IN} in long (about {SIDING_CARS} cars of 50 ft)",
             P4: "Yard tracks Y1 to Y5, {YARD_IN} in long"}


def car_inches(scale_ratio: float | None = None) -> float:
    """The track one 50 ft car takes, coupler allowance included, in inches at the plan's scale."""
    if scale_ratio is None:
        try:
            scale_ratio = float(layer_files.merged_section("staging")["scale_ratio"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LayoutDocsError("build_layout_docs: plan_overrides.json has no staging scale_ratio to count the siding's "
                             f"cars by ({exc!r})") from exc
    return (CAR_FT + COUPLER_FT) * 12 / scale_ratio


def bare(name: str) -> str:
    """A track's name as the page shows it: "S-1" for "Track S-1"; an OS block's in full."""
    return name.removeprefix("Track ")


def turnout(master: Master, did: str) -> DeviceRow:
    """The device master's row of the staging turnout `did` (switch:<n>)."""
    row = master.get((LEVEL, did))
    if row is None or row.layer != "turnout" or row.role != "turnout":
        raise LayoutDocsError(f"build_layout_docs: {did} is no level {LEVEL} turnout of the device master (a switch "
                         "renumbered in the plan changes its ID; fix the template or build_layout_docs.py)")
    return row


def switch_number(master: Master, did: str) -> str:
    """The number in the name of the turnout `did` ("3" for "Switch 3")."""
    name = turnout(master, did).user_name
    m = SWITCH_NAME.fullmatch(name)
    if not m:
        raise LayoutDocsError(f"build_layout_docs: turnout {did} is named {name!r}, not Switch <n>; the page and its plans "
                         "number the switches")
    return m.group(1)


def switches_text(numbers: list[str]) -> str:
    """"Switch 7", or "Switches 7, 23 and 35"."""
    if len(numbers) == 1:
        return f"Switch {numbers[0]}"
    return f"Switches {', '.join(numbers[:-1])} and {numbers[-1]}"


def station_at(stations: list, did: str) -> str:
    """The name of the level 1 station of stations.csv holding the switch of turnout ID `did` (switch:<n>); of two,
    the one with fewer switches (West Yard, not Brick, at Switch 3; Engine House, not Barn, at Switch 9)."""
    n = did.removeprefix("switch:")
    held = sorted((len(s.switches), s.name) for s in stations if str(s.level) == LEVEL and n in s.switches)
    if not held:
        raise LayoutDocsError(f"build_layout_docs: no level {LEVEL} station of stations.csv holds the switch of {did}")
    if len(held) > 1 and held[0][0] == held[1][0]:
        raise LayoutDocsError(f"build_layout_docs: {held[0][1]} and {held[1][1]} both hold the switch of {did}; the "
                         "template names one station")
    return held[0][1]


def label(section: Section, master: Master) -> str:
    """The page's description of a detected section, by its block ID; an OS block's by its turnout's number."""
    if section["id"] in LABELS:
        return LABELS[section["id"]]
    m = OS.fullmatch(section["id"])
    if m:
        number = switch_number(master, f"switch:{m.group(1)}")
        half = re.search(r"([ab])$", section["name"]) if m.group(2) else None
        return f"Turnout {number}{' (crossover half ' + half.group(1) + ')' if half else ''}"
    raise LayoutDocsError(f"build_layout_docs: no label for section {section['id']} ({section['name']}); add it to LABELS")


def master_rows(files: devices.Files | Path | None = None) -> Master:
    """{(level, id): merged device-master row} (hartlib.devices.load: the owner's name wins). `files` a test's copy."""
    return {(r.level_cell, r.id): r for r in devices.load(files) if isinstance(r, DeviceRow) and r.id}


class Section(TypedDict):
    """A row of the page's list of detected sections (detected_sections)."""
    id: str
    name: str
    node: int
    ch: int
    estimate: bool          # no timed length: `inches` is the plan lengths added up
    inches: float


@dataclass
class _Detector:
    """One detector ("Block n-c") as block_lengths.csv's rows on it are read: its section, its parts and lengths."""
    node: int
    ch: int
    id: str | None = None
    name: str | None = None
    plan: float = 0.0
    measured: float | None = None
    parts: list[tuple[str, str]] = field(default_factory=list)     # (part's name, the section it is part of)


def _detectors(lengths: dict[str, block_lengths.Block], master: Master,
               measured: dict[str, block_lengths.Measured]) -> dict[str, _Detector]:
    """{occupancy sensor: _Detector} of the plan's blocks on a "Block n-c" detector, in file order."""
    by_sensor: dict[str, _Detector] = {}
    for b in lengths.values():
        m = re.fullmatch(r"Block (\d+)-(\d+)", b.occupancy_sensor)
        if not m:
            continue
        row = master.get((b.level, b.id))
        if row is None:
            raise LayoutDocsError(f"build_layout_docs: block_lengths.csv line {b.line}: {b.id} is no level {b.level} "
                             "device of the device master")
        d = by_sensor.setdefault(b.occupancy_sensor, _Detector(int(m.group(1)), int(m.group(2))))
        d.plan += b.plan_in
        if row.role == "part":
            d.parts.append((row.user_name, row.part_of))
            continue
        if d.id:
            raise LayoutDocsError(f"build_layout_docs: {b.occupancy_sensor} has two sections, {d.name} and "
                             f"{row.user_name}")
        d.id, d.name = b.id, row.user_name
        if row.user_name in measured:
            d.measured = measured[row.user_name].measured_in
    return by_sensor


def detected_sections(lengths: dict[str, block_lengths.Block] | None = None, master: Master | None = None,
                      measured: dict[str, block_lengths.Measured] | None = None) -> list[Section]:
    """One row per detector ("Block n-c"), by node and channel. Lengths and detectors come from block_lengths.csv
    (by level and ID), names from the device master, so a rename in the field file reaches the page with no build
    step between. A part (role part: a short piece on its OS block's detector) is folded into its block's row. The
    length is the measured one when the detector was timed (it covers the whole detector), else the plan lengths
    added up, marked as an estimate."""
    # the plan lengths in file order, and the measured rows the page prints for a timed detector (hartlib.block_lengths)
    lengths = block_lengths.plan_blocks() if lengths is None else lengths
    measured = block_lengths.measured_lengths() if measured is None else measured
    master = master_rows() if master is None else master
    out: list[Section] = []
    for sensor, d in _detectors(lengths, master, measured).items():
        if d.id is None or d.name is None:
            raise LayoutDocsError(f"build_layout_docs: {sensor} has only parts, no section of its own")
        for piece, owner in d.parts:
            if owner != d.name:
                raise LayoutDocsError(f"build_layout_docs: {piece} is a part of {owner} but is on {sensor}, "
                                 f"{d.name}'s detector")
        out.append({"id": d.id, "name": bare(d.name), "node": d.node, "ch": d.ch, "estimate": d.measured is None,
                    "inches": d.plan if d.measured is None else d.measured})
    return sorted(out, key=lambda s: (s["node"], s["ch"]))


def sections_table(rows: list[Section], master: Master) -> str:
    body = "".join(
        f"<tr><td class=\"num\">{i}</td><td>{html.escape(label(s, master))}</td>"
        f"<td>{html.escape(s['name'])}</td><td>C{s['node']} · {s['ch']}</td>"
        f"<td class=\"num\">{'≈ ' if s['estimate'] else ''}{s['inches']:.0f}</td></tr>"
        for i, s in enumerate(rows, 1))
    return ('<div class="table-wrap">\n        <table class="data-table" id="tab-sections">\n'
            '          <thead><tr><th scope="col">No.</th><th scope="col">Section</th><th scope="col">Layout name</th>'
            '<th scope="col">Node · ch</th><th scope="col">Length, in</th></tr></thead>\n'
            f'          <tbody>{body}</tbody>\n        </table>\n      </div>')


def facts(rows: list[Section], master: Master | None = None) -> dict[str, str]:
    """The figures the page's text states, from the section list and rounded as it shows them. A length from plan
    estimates (marked ≈ in the list) is said as "about". The crossovers are named by their turnouts' numbers."""
    master = master_rows() if master is None else master
    inches = {s["id"]: float(f"{s['inches']:.0f}") for s in rows}
    estimate = {s["id"]: s["estimate"] for s in rows}
    named = {"RS1": [RS1], "SIDING": [SIDING], "YARD": list(YARD)}
    missing = [f"{entry} {bid}" for entry, ids in named.items() for bid in ids if bid not in inches]
    if missing:
        raise LayoutDocsError(f"build_layout_docs: no detected section for {', '.join(missing)}; the page states its "
                         "length (fix the entry in build_layout_docs.py)")

    def about(ids) -> str:
        return "about " if any(estimate[bid] for bid in ids) else ""
    yard = sorted(inches[bid] for bid in YARD)
    xings = sorted({switch_number(master, f"switch:{m.group(1)}") for s in rows
                    if (m := OS.fullmatch(s["id"])) and m.group(2)}, key=int)
    if not xings:
        raise LayoutDocsError("build_layout_docs: no crossover half in the section list; the page names the crossovers")
    listed = switches_text(xings)
    return {"SECTION_COUNT": str(len(rows)), "RS1_IN": f"{about([RS1])}{inches[RS1]:.0f}",
            "SIDING_IN": f"{about([SIDING])}{inches[SIDING]:.0f}", "SIDING_CARS": str(round(inches[SIDING] / car_inches())),
            "YARD_IN": f"{about(YARD)}{yard[0]:.0f} to {yard[-1]:.0f}",
            "CROSSOVERS": f"{'crossovers' if len(xings) > 1 else 'a crossover'} at {listed}"}


def fill_names(text: str, master: Master) -> str:
    """Each {{name:<block id>}} in `text` replaced by the store's name of that staging block."""
    def one(m: re.Match) -> str:
        row = master.get((LEVEL, m.group(1)))
        if row is None:
            raise LayoutDocsError(f"build_layout_docs: the template names {m.group(1)}, no level {LEVEL} device of the "
                             "device master")
        return html.escape(bare(row.user_name))
    return NAME.sub(one, text)


def fill_switches(text: str, master: Master, stations: list) -> str:
    """Each {{turnout:...}}, {{turnouts:...}}, {{dcc:...}} and {{station:...}} in `text` replaced from the device
    master and stations.csv."""
    def one(m: re.Match) -> str:
        kind, arg = m.groups()
        if kind == "turnouts":
            return html.escape(switches_text([switch_number(master, d.strip()) for d in arg.split(",")]))
        if kind == "station":
            turnout(master, arg)
            return html.escape(station_at(stations, arg))
        row = turnout(master, arg)
        if kind == "turnout":
            return html.escape(row.user_name)
        if not row.dcc:
            raise LayoutDocsError(f"build_layout_docs: turnout {arg} has no DCC address in the device master")
        return html.escape(row.dcc)
    return SWITCHES.sub(one, text)


def check_d2(count: int) -> None:
    """Drawing D2 says how many sections are wired its way; it must match the section list."""
    if not D2.is_file():
        raise LayoutDocsError(f"build_layout_docs: {D2.relative_to(ROOT)} is missing; the section count check reads it")
    said = re.search(r"All (\d+) detected sections", D2.read_text())
    if not said or int(said.group(1)) != count:
        raise LayoutDocsError(f"build_layout_docs: {D2.relative_to(ROOT)} says {said.group(1) if said else 'no'} detected "
                         f"sections, block_lengths.csv has {count}; edit the drawing")


def check_plans(fact: dict[str, str]) -> None:
    """Plans P3 and P4 state the siding's and the yard's lengths; they must be the page's."""
    for svg, text in PLAN_TEXT.items():
        want = text.format(**fact)
        if want not in svg.read_text():
            raise LayoutDocsError(f"build_layout_docs: {svg.relative_to(ROOT)} must say {want!r}, as the section list "
                             "does; edit the drawing")


def drawn_switches(svg: str) -> list[str]:
    """The switch numbers a plan's switch labels print, in number order."""
    out = set()
    for attrs, body in re.findall(r"<text\b([^>]*)>([^<]*)<", svg):
        body = body.strip()
        if m := P0_LABEL.fullmatch(body):
            out.add(m.group(1))
        elif body.isdigit() and all(a in attrs for a in LABEL_STYLE):
            out.add(body)
    return sorted(out, key=int)


def check_switch_labels(master: Master, plans=PLANS) -> None:
    """The plans (hand-edited files) label every staging switch by its number ("Sw 3" on plan P0, "3" on the others);
    they must label the live turnouts' numbers, so a switch renumbered or renamed stops here until they are edited."""
    live = sorted({switch_number(master, k[1]) for k, r in master.items()
                   if k[0] == LEVEL and r.layer == "turnout" and r.role == "turnout"}, key=int)
    for svg in plans:
        drawn = drawn_switches(Path(svg).read_text())
        if drawn != live:
            raise LayoutDocsError(f"build_layout_docs: {Path(svg).name} labels switches {', '.join(drawn)}, the "
                             f"device master has {', '.join(live)}; edit the drawing")


def svg_texts(svg: str) -> list[tuple[str, str]]:
    """(attributes, plain text) of each <text>, <tspan>, <title> and <desc> in `svg`, inner tags stripped."""
    return [(attrs, html.unescape(re.sub(r"<[^>]*>", "", inner)).strip())
            for _, attrs, inner in SVG_TEXT.findall(svg)]


def check_station_labels(stations: list, master: Master, drawings=None) -> None:
    """The drawings (hand-edited files) name a station only in a data-station label, and each such label holds the
    name stations.csv gives the station at that switch; so a station renamed there stops here until they are edited."""
    names = {s.name.casefold() for s in stations if str(s.level) == LEVEL}
    for svg in sorted(DRAWINGS.glob("*.svg")) if drawings is None else drawings:
        text = Path(svg).read_text()
        tagged = [(m.group(1), body) for attrs, body in svg_texts(text) if (m := DATA_STATION.search(attrs))]
        for did, body in tagged:
            turnout(master, did)
            want = station_at(stations, did)
            if body != want:
                raise LayoutDocsError(f"build_layout_docs: {Path(svg).name} labels the station at {did} {body!r}, "
                                 f"stations.csv has {want!r}; edit the drawing")
        untagged = SVG_TEXT.sub(lambda m: "" if DATA_STATION.search(m.group(2)) else m.group(0), text)
        tspans = [html.unescape(re.sub(r"<[^>]*>", "", t)).strip() for t in TSPAN.findall(untagged)]
        for body in [b for _, b in svg_texts(untagged)] + tspans:
            if body.casefold() in names:
                raise LayoutDocsError(f"build_layout_docs: {Path(svg).name} names {body} outside a data-station label; "
                                 "label it <text data-station=\"switch:<n>\"> so the build checks it against "
                                 "stations.csv")


def check_drawings() -> None:
    """No SOQ wording in the visible text of the page's drawings."""
    for svg in sorted(DRAWINGS.glob("*.svg")):
        text = " ".join(re.findall(r"<(?:text|tspan|title|desc)\b[^>]*>([^<]*)", svg.read_text()))
        for word in SOQ_WORDS:
            if word in text:
                raise LayoutDocsError(f"build_layout_docs: {svg.relative_to(ROOT)} says {word!r}, SOQ wording; edit the drawing")


def outputs(files=None, stations: Path | None = None, plans=None, drawings=None) -> dict[Path, str]:
    """The page. `files` is the device master's (hartlib.devices.Files of a test's copy), `stations` a copy of
    stations.csv, `plans` copies of the plans and `drawings` copies of all the drawings; None the repo's."""
    master = master_rows(files)
    places = railroad.read_stations(railroad.Sources.under().stations if stations is None else stations)
    rows = detected_sections(master=master)
    fact = facts(rows, master)
    page = fill_switches(fill_names(TEMPLATE.read_text(), master), master, places)
    page = page.replace("{{SECTIONS_TABLE}}", sections_table(rows, master))
    for key, value in fact.items():
        page = page.replace("{{" + key + "}}", value)
    if "{{" in page:
        raise LayoutDocsError("build_layout_docs: a placeholder is left in the page")
    check_d2(len(rows))
    check_plans(fact)
    check_switch_labels(master, PLANS if plans is None else plans)
    check_station_labels(places, master, drawings)
    check_drawings()
    return {PAGE: page}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="report stale outputs and exit 1, write nothing")
    a = ap.parse_args()
    stale = []
    try:
        built = outputs()
    except LayoutDocsError as exc:
        raise SystemExit(str(exc)) from exc
    for path, text in built.items():
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
