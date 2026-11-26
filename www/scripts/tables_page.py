"""Facts about the JMRI tables file, and the tables file page filled from them.

behind/tables-file.html marks every number, name and excerpt that describes
tables.xml with a region:

    <!--tf:lines-->28,752<!--/tf-->

fill() replaces each region's contents with the value worked out from the file,
so the page cannot drift from it. build_tables_browser.py writes the page with
the browser data and checks both in tools/check.sh; prepare_github_pages.py
fills the built copy on every site build.

A region the code does not know, a known region missing from the page, or a
named example that no longer exists in the file in the form the prose
describes stops the build with a message. Fix the page text or the example
name; never type a number into a region by hand.
"""
from __future__ import annotations

import collections
import html
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict, cast

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
import xml.etree.ElementTree as ET  # noqa: E402

from hartlib import level_devices, parked, paths, railroad_facts, tables  # noqa: E402

REGION = re.compile(r"<!--tf:([a-z0-9-]+)-->(.*?)<!--/tf-->", re.S)

# Hand-picked examples. Each must still exist in the file in the form the page describes.
EXAMPLE_SENSOR = "BS K-1"
EXAMPLE_BLOCK, EXAMPLE_BLOCK_TURNOUT = "OS Switch 13", "Switch 13"
# The switch facts (ADR-021): the example block's closed and thrown legs, which JMRI's paths follow. The generated
# tables.xml stores no block paths (ADR-029: JMRI works them out from the panel when it loads the file).
SWITCHES = paths.LAYOUT_DATA / "switches.csv"
EXAMPLE_SML = ("Mast 40LA", "Mast 24L")
EXAMPLE_TURNOUT = "Switch 35"
EXAMPLE_DETECTORS: tuple[str, ...] = ()   # none is shared since the yard throats went (2026-11-20)

# Top-level sections in groups. Consecutive sections of one group share a row on the page.
# A section not listed here stops the build: describe it before it reaches the page.
GROUPS = {
    "jmriversion": ("start", "JMRI version", "The version of JMRI that stored the file."),
    "sensors": ("objects", "Sensors", "Inputs: occupancy and switch feedback from the layout, plus internal flags and helpers."),
    "turnouts": ("objects", "Turnouts", "The switches, their DCC twins, and internal turnouts for the main and upper levels."),
    "memories": ("objects", "Memories", "Small stored values, such as the fast-clock time and the mimic page's requests."),
    "signalheads": ("objects", "Signal heads", "Virtual heads that carry each lamp's colour."),
    "signalmasts": ("objects", "Signal masts", "The signals, real and virtual, all stock Basic."),
    "blocks": ("objects", "Blocks", "Stretches of track, each with an occupancy sensor and paths to its neighbours."),
    "layoutblocks": ("objects", "Layout blocks", "The Layout Editor's view of each block."),
    "sections": ("objects", "Sections", "Dispatcher track pieces, mostly made from pairs of masts."),
    "transits": ("objects", "Transits", "Whole moves that the Dispatcher builds from sections."),
    "routes": ("objects", "Routes", "Sets of switches thrown together. None since the yard-ladder buttons were retired."),
    "signalmastlogics": ("objects", "Signal Mast Logic", "The rules that set a mast from the track ahead."),
    "logixs": ("objects", "Logix", None),  # filled with the count
    "conditionals": ("objects", "Conditionals", "The conditions and actions inside those Logix."),
    "timebase": ("objects", "Fast clock", "The settings of JMRI's fast clock."),
    "LogixNGs": ("objects", "LogixNG", 'Newer logic that <a href="#logixng">hides windows and clears the main and upper block sensors at startup</a>: the LogixNGs, their ConditionalNGs and their actions.'),
    "LogixNGConditionalNGs": ("objects", "LogixNG", None),
    "LogixNGDigitalActions": ("objects", "LogixNG", None),
    "ctcdata": ("objects", "CTC data", "The USS CTC machine's code buttons and settings."),
    "entryexitpairs": ("objects", "Entry/Exit", "Pairs that line a route from a click on the panel."),
    "paneleditor": ("panels", None, None),
    "LayoutEditor": ("panels", None, None),
    "filehistory": ("end", "File history", "A short record of loads and stores."),
}
GROUP_HEADS = {"start": "At the start", "objects": "Objects", "panels": "Panels", "end": "At the end"}
# What each panel is. A panel not listed here stops the build.
PANELS = {
    "USS CTC": "The lever machine, a Panel Editor screen.",
    "HART Railroad": "The track diagram, a Layout Editor panel.",
    "Staging Level": "The staging level alone, a copy of the track diagram; hidden when the file loads.",
    "Main Level": "The main level alone, a copy of the track diagram; hidden when the file loads.",
    "Upper Level": "The upper level alone, a copy of the track diagram; hidden when the file loads.",
    "Dispatcher System": "A Layout Editor panel drawn by the Dispatcher System package.",
}
# The parked features (hartlib.parked.PARKED): their sections and panels are not in the file; the page lists them in
# their place with this note, and says so under the title.
PARKED_NOTE = ("Parked since the helix-join release (November 2026): not in the active panel; data kept in "
               "jmri/layouts/hart/parked/.")
BAR_X, BAR_W = 8, 344  # the drawn-to-scale bar in the page's 360-wide figure
SETTINGS = {"2": "Closed", "4": "Thrown"}  # JMRI turnout states in a block path
WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()


class PageError(SystemExit):
    """The page and the file disagree in a way only a person can fix."""


class Row(TypedDict):
    """One row of the sections table: a group of top-level sections, a panel, or a parked section."""
    group: str
    label: str
    note: str | None  # None: the Logix row, whose note is the count
    share: float
    parked: bool


class Block(TypedDict):
    """The example block, its sensor, and the legs its switch leads to."""
    name: str
    sensor: str
    turnout: str
    closed: str
    thrown: str


class Clear(TypedDict):
    """The LogixNG that sets the main and upper block sensors clear."""
    name: str
    count: int
    turnouts: int
    thrown: str


class LogixNG(TypedDict):
    """The Initialization Table's LogixNG: (ConditionalNG, action kind, what it does, script name or "")."""
    name: str
    rows: list[tuple[str, str, str, str]]


class Facts(TypedDict):
    """Everything the page says about the file (facts()); regions() turns it into the page's text."""
    version: str
    bytes: int
    lines: int
    top: int
    rows: list[Row]
    share: dict[str, float]
    parked: list[str]
    panels: int
    largest: tuple[str, float]
    layoutBlocks: int
    detectors: int
    paths: int
    sharedCount: int
    sharedExamples: list[tuple[str, list[str]]]
    sensor: tuple[str, str, str]  # system name, user name, comment
    block: Block
    sml: dict[str, str]  # src, dst and the destination's flags, by their tables.xml names
    turnout: tuple[str, str, str]  # user name, sensor1, sensor2
    ctcColumns: int
    logix: int
    logixng: LogixNG
    clear: Clear


def word(n: int) -> str:
    return WORDS[n] if 0 <= n < len(WORDS) else f"{n:,}"


def count(n: int, one: str, many: str) -> str:
    """"one detector", "seven detectors"."""
    return f"{word(n)} {one if n == 1 else many}"


def pct(share: float) -> str:
    return "under 1%" if share < 0.005 else f"{round(share * 100)}%"


def and_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _sections(raw: bytes) -> list[tuple[str, int, str]]:
    """Top-level sections in file order: (tag, bytes, panel name or "")."""
    found = [(m.start(), m.group(1).decode(), m.group(2)) for m in
             re.finditer(rb'\n  <([A-Za-z]+)((?:\s[^>]*)?)/?>', raw)]
    if not found:
        raise PageError("tables.xml: no top-level sections found")
    out = []
    for i, (start, tag, attrs) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else raw.rindex(b"</layout-config>")
        name = re.search(rb'\sname="([^"]*)"', attrs) if tag in ("paneleditor", "LayoutEditor") else None
        out.append((tag, end - start, html.unescape(name.group(1).decode()) if name else ""))
    return out


def _one(items: list[ET.Element], what: str) -> ET.Element:
    if len(items) != 1:
        raise PageError(f"tables.xml: expected one {what}, found {len(items)}")
    return items[0]


def facts(raw: bytes, root: ET.Element) -> Facts:
    """Everything the page says about the file, worked out from it."""
    f: dict = {"version": _version(root), "bytes": len(raw), "lines": raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1)}
    f.update(_layout(raw, root))
    f.update(_detectors(root))
    f.update(_examples(root))
    ctc = root.find("ctcdata")
    if ctc is None and "uss" in parked.PARKED:      # the CTC data is parked with the USS CTC machine
        ctc = next((t.find("ctcdata") for t in parked.read().iter("tables") if t.find("ctcdata") is not None), None)
    f["ctcColumns"] = len(ctc.findall("ctcCodeButtonData")) if ctc is not None else 0
    f["logix"] = len(tables.section(root, "logixs", "logix"))
    f.update(_logixng(root))
    missing = sorted(set(Facts.__annotations__) - set(f))
    if missing:
        raise PageError(f"{Path(__file__).name}: facts() did not work out {', '.join(missing)}")
    return cast(Facts, f)  # the parts fill it key by key; every key is checked just above


def _version(root: ET.Element) -> str:
    """The JMRI version the file was stored by, such as 5.13.1."""
    jv = root.find("jmriversion")
    if jv is None:
        raise PageError("tables.xml: no <jmriversion>")
    ver = f"{jv.findtext('major')}.{jv.findtext('minor')}"
    if (jv.findtext("test") or "0") != "0":
        ver += f".{jv.findtext('test')}"
    modifier = (jv.findtext("modifier") or "").strip()
    if modifier:
        ver += modifier
    return ver


def _layout(raw: bytes, root: ET.Element) -> dict:
    """The table of the file's top-level sections by group, with their shares of the file and the parked rows."""
    f: dict = {}
    secs = _sections(raw)
    if len(secs) != len(list(root)):
        raise PageError(f"tables.xml: found {len(secs)} sections by text but {len(list(root))} by XML")
    f["top"] = len(secs)
    total = sum(n for _, n, _ in secs)
    share: dict[str, float] = {}
    rows: list[Row] = []
    for tag, n, name in secs:
        if tag not in GROUPS:
            raise PageError(f"tables.xml has a top-level <{tag}> the page does not describe; add it to GROUPS in {Path(__file__).name}")
        group, label, note = GROUPS[tag]
        share[group] = share.get(group, 0.0) + n / total
        if group == "panels":
            if name not in PANELS:
                raise PageError(f"tables.xml has a panel {name!r} the page does not describe; add it to PANELS in {Path(__file__).name}")
            label, note = name, PANELS[name]
        if label is None:
            raise PageError(f"GROUPS[{tag!r}] has no label and is not a panel")
        if rows and rows[-1]["group"] == group and rows[-1]["label"] == label:
            rows[-1]["share"] += n / total
            continue
        rows.append({"group": group, "label": label, "note": note, "share": n / total, "parked": False})
    _add_parked_rows(rows, parked.PARKED, {tag for tag, _n, _name in secs}, {name for _t, _n, name in secs if name})
    f["rows"], f["share"] = rows, dict(share)
    f["parked"] = sorted(parked.PARKED)
    f["panels"] = sum(1 for r in rows if r["group"] == "panels" and not r["parked"])
    biggest = max(rows, key=lambda r: r["share"])
    f["largest"] = (biggest["label"], biggest["share"])
    return f


def _detectors(root: ET.Element) -> dict:
    """Layout blocks and the detectors they share; the file stores no block paths."""
    f: dict = {}
    blocks = tables.blocks(root)
    lbs = tables.layout_blocks(root)
    # A layout block may name its sensor by system or user name; count each sensor once.
    sensor_user = {e.findtext("systemName"): e.findtext("userName") or e.findtext("systemName")
                   for e in tables.sensors(root)}
    users = collections.defaultdict(list)
    for lb in lbs:
        occ = lb.get("occupancysensor") or ""
        users[sensor_user.get(occ, occ)].append(lb.findtext("userName") or lb.findtext("systemName"))
    users.pop("", None)
    f["layoutBlocks"], f["detectors"] = len(lbs), len(users)
    f["paths"] = sum(len(b.findall("path")) for b in blocks)
    if f["paths"]:
        raise PageError(f"tables.xml stores {f['paths']} block paths; the generated file stores none (ADR-029), and "
                        "the page says so")
    shared = {d: u for d, u in users.items() if len(u) > 1}
    f["sharedCount"] = len(shared)
    f["sharedExamples"] = []
    for d in EXAMPLE_DETECTORS:
        if d not in shared:
            raise PageError(f"tables.xml: detector {d!r} is no longer shared by several layout blocks; pick another in EXAMPLE_DETECTORS")
        f["sharedExamples"].append((d, shared[d]))
    return f


def _examples(root: ET.Element) -> dict:
    """The example sensor, block, Signal Mast Logic and turnout the page quotes."""
    f: dict = {}
    s = _one([e for e in tables.sensors(root) if e.findtext("userName") == EXAMPLE_SENSOR],
             f"sensor named {EXAMPLE_SENSOR!r}")
    f["sensor"] = (s.findtext("systemName"), EXAMPLE_SENSOR, (s.findtext("comment") or "").strip())
    if not f["sensor"][2]:
        raise PageError(f"tables.xml: sensor {EXAMPLE_SENSOR!r} has no comment, and the page quotes it")

    b = _one([e for e in tables.blocks(root) if e.findtext("userName") == EXAMPLE_BLOCK],
             f"block named {EXAMPLE_BLOCK!r}")
    try:
        legs = [r for r in railroad_facts.read_switch_rows(SWITCHES) if r.os_block == EXAMPLE_BLOCK
                and f"Switch {r.switch}" == EXAMPLE_BLOCK_TURNOUT]
    except railroad_facts.FactsError as exc:
        raise PageError(str(exc)) from exc
    if len(legs) != 1:
        raise PageError(f"{SWITCHES.name}: block {EXAMPLE_BLOCK!r} no longer has one row with a closed and a thrown "
                        f"leg for {EXAMPLE_BLOCK_TURNOUT!r}: {legs}")
    f["block"] = {"name": EXAMPLE_BLOCK, "sensor": b.findtext("occupancysensor") or "", "turnout": EXAMPLE_BLOCK_TURNOUT,
                  "closed": legs[0].closed_leg, "thrown": legs[0].thrown_leg}
    if not f["block"]["sensor"]:
        raise PageError(f"tables.xml: block {EXAMPLE_BLOCK!r} has no occupancy sensor")

    src, dst = EXAMPLE_SML
    sml = _one([e for e in tables.section(root, "signalmastlogics", "signalmastlogic")
                if e.findtext("sourceSignalMast") == src],
               f"Signal Mast Logic from {src!r}")
    d = _one([x for x in sml.findall("destinationMast") if x.findtext("destinationSignalMast") == dst],
             f"Signal Mast Logic destination {src!r} to {dst!r}")
    keys = ("enabled", "useLayoutEditor", "useLayoutEditorTurnouts", "useLayoutEditorBlocks", "associatedSection")
    f["sml"] = {"src": src, "dst": dst, **{k: (d.findtext(k) or "").strip() for k in keys}}
    section_names: set[str | None] | None = {n for e in tables.section(root, "sections", "section")
                     for n in (e.findtext("systemName"), e.findtext("userName"))}
    if not f["sml"]["associatedSection"] and "dispatcher" in parked.PARKED:
        # the Dispatcher's sections are parked (hartlib.parked): the pair's section is named in the parked file
        f["sml"]["associatedSection"], section_names = _parked_section(src, dst), None
    if section_names is not None and f["sml"]["associatedSection"] not in section_names:
        raise PageError(f"tables.xml: section {f['sml']['associatedSection']!r} named by {src} to {dst} does not exist")

    t = _one([e for e in tables.turnouts(root) if e.findtext("userName") == EXAMPLE_TURNOUT],
             f"turnout named {EXAMPLE_TURNOUT!r}")
    if t.get("feedback") != "TWOSENSOR" or not (t.get("sensor1") and t.get("sensor2")):
        raise PageError(f"tables.xml: turnout {EXAMPLE_TURNOUT!r} no longer reports through two sensors, as the page says")
    f["turnout"] = (EXAMPLE_TURNOUT, t.get("sensor1"), t.get("sensor2"))
    return f


def _logixng(root: ET.Element) -> dict:
    """Two LogixNGs: the one in the Initialization Table, its ConditionalNGs and their single actions; and the one
    that sets the main and upper virtual block sensors clear (hartlib.tables_build.start_logixng)."""
    f: dict = {}
    init = [x.text for m in root.findall("LogixNGs") for it in m.findall("InitializationTable") for x in it.findall("LogixNG")]
    ngs = tables.section(root, "LogixNGs", "LogixNG")
    ng = _one([n for n in ngs if n.findtext("systemName") in init], "LogixNG in the Initialization Table")
    ng_sys = ng.findtext("systemName")
    cng = {c.findtext("systemName"): c for c in tables.section(root, "LogixNGConditionalNGs", "ConditionalNG")}
    acts = {a.findtext("systemName"): a for m in root.findall("LogixNGDigitalActions") for a in m}
    clear = _one([n for n in ngs if n is not ng], "LogixNG besides the Initialization Table's")
    cs = [cng.get(x.text) for x in clear.findall("ConditionalNGs/systemName")]
    try:
        sensors = level_devices.clear_sensors(root)
    except ValueError as exc:
        raise PageError(f"tables.xml: {exc}") from exc
    if clear.findtext("systemName") != level_devices.CLEAR_LOGIXNG or len(cs) != 1 or cs[0] is None \
            or cs[0].findtext("Socket/systemName") != level_devices.CLEAR_MANY or not sensors \
            or not all(level_devices.is_block_sensor(x) for x in sensors):
        raise PageError(f"tables.xml: LogixNG {clear.findtext('systemName')} no longer sets the main and upper "
                        "block sensors clear, as the page says")
    try:
        states = level_devices.turnout_states(root)
    except ValueError as exc:
        raise PageError(f"tables.xml: {exc}") from exc
    thrown = sorted((t.removeprefix(level_devices.TURNOUT_PREFIX) for t, st in states.items() if st == "Thrown"),
                    key=lambda n: (len(n), n))
    f["clear"] = {"name": clear.findtext("userName") or clear.findtext("systemName"), "count": len(sensors),
                  "turnouts": len(states),
                  "thrown": ("Switches " + ", ".join(thrown[:-1]) + " and " + thrown[-1]) if len(thrown) > 1 else
                            (f"Switch {thrown[0]}" if thrown else "none")}
    rows = []
    listed = ng.find("ConditionalNGs")
    for sysname in [x.text for x in listed.findall("systemName")] if listed is not None else []:
        c = cng.get(sysname)
        if c is None:
            raise PageError(f"tables.xml: LogixNG {ng_sys} lists ConditionalNG {sysname}, which does not exist")
        socks = c.findall("Socket")
        if len(socks) != 1:
            raise PageError(f"tables.xml: ConditionalNG {sysname} has {len(socks)} actions; the page says one each")
        a = acts.get(socks[0].findtext("systemName") or "")
        if a is None:
            raise PageError(f"tables.xml: ConditionalNG {sysname} has no connected action; the page lists one")
        if a.tag == "DisplayActionWindowManagement" and a.findtext("hideOrShow/enum") == "Hide":
            what = ("Window Management", f"hides the {a.findtext('jmriJFrameTitle')} window", "")
        elif a.tag == "ActionScript" and a.findtext("operationType") == "RunScript":
            what = ("Run Script", "runs ", (a.findtext("script") or "").rsplit("/", 1)[-1])
        else:
            raise PageError(f"tables.xml: ConditionalNG {sysname} has a {a.tag} action the page does not describe")
        rows.append((c.findtext("userName") or sysname, *what))
    if sum(1 for r in rows if r[3]) != 2:
        raise PageError("tables.xml: the page says two ConditionalNGs run a script; "
                        f"{sum(1 for r in rows if r[3])} do")
    f["logixng"] = {"name": ng.findtext("userName") or ng_sys, "rows": rows}
    return f


def _add_parked_rows(rows: list[Row], features: Iterable[str], tags: set[str], panel_names: set[str]) -> None:
    """Put a row for each parked section and panel the file no longer holds in its place among `rows` (GROUPS and
    PANELS order), marked Parked, with no share of the file."""
    order = list(GROUPS)
    panel_order = list(PANELS)

    def key(r: Row) -> tuple[int, int]:
        if r["group"] == "panels":
            return order.index("paneleditor"), panel_order.index(r["label"]) if r["label"] in panel_order else 99
        tag = next((t for t, g in GROUPS.items() if g[1] == r["label"] and g[0] == r["group"]), None)
        return (order.index(tag) if tag else 99), 0

    added: set[str] = set()
    for feature in sorted(features):
        # its whole sections, and the Logix sections it empties (both Logix are parked)
        whole = parked.WHOLE.get(feature, ()) + (("logixs", "conditionals") if feature in parked.LOGIX else ())
        new = [(t, GROUPS[t] if GROUPS[t][2] else (*GROUPS[t][:2], "Older-style logic items."))
               for t in whole if t not in tags and t in GROUPS and t not in added]
        added.update(t for t, _g in new)
        if feature in parked.PANELS and parked.PANELS[feature][1] not in panel_names:
            title = parked.PANELS[feature][1]
            new.append((title, ("panels", title, PANELS.get(title, ""))))
        for tag, (group, label, note) in new:
            if label is None:
                raise PageError(f"GROUPS[{tag!r}] has no label for its parked row")
            row: Row = {"group": group, "label": label, "note": f"{note} Parked.", "share": 0.0, "parked": True}
            k = key(row)
            at = next((i for i, r in enumerate(rows) if key(r) > k), len(rows))
            rows.insert(at, row)


def _parked_section(src: str, dst: str) -> str:
    """The section the parked file names for the Signal Mast Logic pair src -> dst."""
    for b in parked.read().iter("binding"):
        if (b.get("element"), b.get("ident"), b.get("destination"), b.get("child")) == (
                "signalmastlogic", src, dst, "associatedSection"):
            return b.get("value") or ""
    raise PageError(f"the parked file names no section for the Signal Mast Logic {src} to {dst}; pick another "
                    f"EXAMPLE_SML")


def _xml(lines: list[str]) -> str:
    return html.escape("\n".join(lines), quote=False)


def bar(obj: float, pan: float) -> str:
    """The drawn-to-scale Objects / Panels / rest bar."""
    x, rects, texts, done = BAR_X, [], [], 0.0
    for cls, label, share, tcls in (("own", "Objects", obj, "t-b t-w"), ("acc", "Panels", pan, "t-b t-d")):
        # Round the running edge, not each width, and leave 1px for the rest, so nothing runs past the bar.
        w = min(round(BAR_W * (done + share)), BAR_W - 1) - min(round(BAR_W * done), BAR_W - 1)
        done += share
        rects.append(f'<rect class="{cls}" x="{x}" y="14" width="{w}" height="34" rx="3"/>')
        texts.append(f'<text class="{tcls}" x="{x + w // 2}" y="36" text-anchor="middle">{label}</text>')
        x += w
    rects.append(f'<rect class="own" x="{x}" y="14" width="{max(1, BAR_X + BAR_W - x)}" height="34" rx="3" '
                 'style="fill:var(--muted);stroke:var(--muted)"/>')
    return "\n          ".join(rects + texts)


def _e(s: object) -> str:
    return html.escape(str(s), quote=False)


def _section_rows(f: Facts) -> str:
    """The sections table's rows, a heading row before each group."""
    body, group = [], None
    for r in f["rows"]:
        if r["group"] != group:
            group = r["group"]
            body.append(f'<tr><td colspan="3"><strong>{GROUP_HEADS[group]}</strong></td></tr>')
        note = r["note"] if r["note"] is not None else f"{count(f['logix'], 'older-style logic item', 'older-style logic items').capitalize()}."
        share = "parked" if r.get("parked") else pct(r["share"])
        body.append(f'<tr><td>{_e(r["label"])}</td><td>{note}</td><td class="num">{share}</td></tr>')
    return "\n            ".join(body)


def _shared_sentence(f: Facts) -> str:
    """How many detectors several layout blocks share, with the named examples."""
    n = f["sharedCount"]
    if n == 0:
        return "No detector is shared."
    ex = [f'"{_e(d)}" serves {_e(and_list(u))}' for d, u in f["sharedExamples"]]
    return f"{count(n, 'detector', 'detectors').capitalize()} {'is' if n == 1 else 'are'} shared." + (f" {', and '.join(ex)}." if ex else "")


def _block_xml(blk: Block) -> str:
    return _xml(["<block>", f"  <userName>{blk['name']}</userName>", f"  <occupancysensor>{blk['sensor']}</occupancysensor>",
                 "</block>"])


def _sml_xml(s: dict[str, str]) -> str:
    sx = [f'<signalmastlogic source="{s["src"]}">', f'  <destinationMast destination="{s["dst"]}">']
    sx += [f"    <{k}>{s[k]}</{k}>" for k in ("enabled", "useLayoutEditor", "useLayoutEditorTurnouts",
                                           "useLayoutEditorBlocks", "associatedSection")]
    sx += ["  </destinationMast>", "</signalmastlogic>"]
    return _xml(sx)


def _turnout_xml(turnout: tuple[str, str, str]) -> str:
    name, s1, s2 = turnout
    return _xml(['<turnout feedback="TWOSENSOR"', f'         sensor1="{s1}"', f'         sensor2="{s2}">',
                 f"  <userName>{name}</userName>", "</turnout>"])


def _logixng_rows(ng: LogixNG) -> str:
    return "\n            ".join(
        f"<tr><td>{_e(n)}</td><td>{_e(kind)}: {_e(what)}{f'<code>{_e(code)}</code>' if code else ''}</td></tr>"
        for n, kind, what, code in ng["rows"])


def regions(f: Facts) -> dict[str, str]:
    """Each region's HTML."""
    e = _e
    obj, pan = f["share"].get("objects", 0), f["share"].get("panels", 0)
    blk, s = f["block"], f["sml"]
    sys_name, user, comment = f["sensor"]
    return {
        "version": e(f["version"]),
        "size": f"{f['bytes'] / 1e6:.1f} MB",
        "lines": f"{f['lines']:,}",
        "top": str(f["top"]),
        "sensor-pair": _xml([f"systemName  {sys_name}", f"userName    {user}"]),
        "sensor-user": e(user),
        "sensor-comment": e(comment),
        "objects": f"{max(1, round(obj * 100))}%",  # prose says "about N%", so never "under 1%"
        "panels": f"{max(1, round(pan * 100))}%",
        "panel-count": count(f["panels"], "panel", "panels"),
        "bar": bar(obj, pan),
        "largest": e(f["largest"][0]),
        "largest-share": pct(f["largest"][1]),
        "sections": _section_rows(f),
        "layout-blocks": str(f["layoutBlocks"]),
        "detectors": str(f["detectors"]),
        "shared": _shared_sentence(f),
        "block-name": e(blk["name"]),
        "block-sensor": e(blk["sensor"]),
        "block-xml": _block_xml(blk),
        "block-sentence": (f"from {e(blk['name'])} you can go to {e(blk['closed'])} when {e(blk['turnout'])} is closed, "
                           f"and to {e(blk['thrown'])} when it is thrown"),
        "sml-xml": _sml_xml(s),
        "sml-section": e(s["associatedSection"]),
        "parked": parked_note(f["parked"]),
        "sml-parked": (" Sections, transits and Entry/Exit are parked since the helix-join release (November 2026); "
                       "the masts and pairs stay live." if {"dispatcher", "nx"} <= set(f["parked"]) else ""),
        "turnout-xml": _turnout_xml(f["turnout"]),
        "ctc-columns": str(f["ctcColumns"]),
        "logixng-name": e(f["logixng"]["name"]),
        "logixng-count": count(len(f["logixng"]["rows"]), "ConditionalNG", "ConditionalNGs"),
        "logixng-rows": _logixng_rows(f["logixng"]),
        "clear-name": e(f["clear"]["name"]),
        "clear-count": str(f["clear"]["count"]),
        "clear-turnouts": str(f["clear"]["turnouts"]),
        "clear-thrown": e(f["clear"]["thrown"]),
    }


def parked_note(features: list[str]) -> str:
    """The note under the page's title while features are parked (none when nothing is)."""
    if not features:
        return ""
    names = {"nx": "the Entry/Exit pairs", "dispatcher": "the Dispatcher System with its sections and transits",
             "uss": "the USS CTC machine with its CTC data"}
    return (f"<strong>Parked.</strong> Since the helix-join release (November 2026) "
            f"{and_list([names[x] for x in ('nx', 'dispatcher', 'uss') if x in features])} are not in the active "
            f"file; their data is kept in <code>jmri/layouts/hart/parked/</code>. The table below lists them in their "
            f"place.")


def fill(page: str, f: Facts) -> str:
    """The page with every region replaced; stops on an unknown or missing region."""
    values = regions(f)
    seen = set()

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise PageError(f"tables-file.html has a region tf:{key} that {Path(__file__).name} does not fill")
        seen.add(key)
        return f"<!--tf:{key}-->{values[key]}<!--/tf-->"

    out = REGION.sub(sub, page)
    missing = sorted(set(values) - seen)
    if missing:
        raise PageError(f"tables-file.html is missing regions: {', '.join('tf:' + k for k in missing)}")
    return out
