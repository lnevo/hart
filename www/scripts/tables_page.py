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
from pathlib import Path

REGION = re.compile(r"<!--tf:([a-z0-9-]+)-->(.*?)<!--/tf-->", re.S)

# Hand-picked examples. Each must still exist in the file in the form the page describes.
EXAMPLE_SENSOR = "BS K-1"
EXAMPLE_BLOCK, EXAMPLE_BLOCK_TURNOUT = "OS Switch 13", "Switch 13"
EXAMPLE_SML = ("Mast 2036", "Mast 38LB")
EXAMPLE_TURNOUT = "Switch 35"
EXAMPLE_DETECTORS = ("BS S-1", "BS Switch 37 / BS McKeesport")

# Top-level sections in groups. Consecutive sections of one group share a row on the page.
# A section not listed here stops the build: describe it before it reaches the page.
GROUPS = {
    "jmriversion": ("start", "JMRI version", "The version of JMRI that stored the file."),
    "sensors": ("objects", "Sensors", "Inputs: occupancy and switch feedback from the layout, plus internal flags and helpers."),
    "turnouts": ("objects", "Turnouts", "The switches, their DCC twins, and internal turnouts for the yard ladders."),
    "memories": ("objects", "Memories", "Small stored values, such as the fast-clock time and the mimic page's requests."),
    "signalheads": ("objects", "Signal heads", "Virtual heads that carry each lamp's colour."),
    "signalmasts": ("objects", "Signal masts", "The signals, real and virtual, all stock Basic."),
    "blocks": ("objects", "Blocks", "Stretches of track, each with an occupancy sensor and paths to its neighbours."),
    "layoutblocks": ("objects", "Layout blocks", "The Layout Editor's view of each block."),
    "sections": ("objects", "Sections", "Dispatcher track pieces, mostly made from pairs of masts."),
    "transits": ("objects", "Transits", "Whole moves that the Dispatcher builds from sections."),
    "routes": ("objects", "Routes", "Sets of switches thrown together, used by the yard ladders."),
    "signalmastlogics": ("objects", "Signal Mast Logic", "The rules that set a mast from the track ahead."),
    "logixs": ("objects", "Logix", None),  # filled with the count
    "conditionals": ("objects", "Conditionals", "The conditions and actions inside those Logix."),
    "timebase": ("objects", "Fast clock", "The settings of JMRI's fast clock."),
    "LogixNGs": ("objects", "LogixNG", 'Newer logic that <a href="#logixng">hides windows at startup</a>: the LogixNG, its ConditionalNGs and their actions.'),
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
    "Dispatcher System": "A Layout Editor panel drawn by the Dispatcher System package.",
}
BAR_X, BAR_W = 8, 344  # the drawn-to-scale bar in the page's 360-wide figure
SETTINGS = {"2": "Closed", "4": "Thrown"}  # JMRI turnout states in a block path
WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()


class PageError(SystemExit):
    """The page and the file disagree in a way only a person can fix."""


def word(n: int) -> str:
    return WORDS[n] if 0 <= n < len(WORDS) else f"{n:,}"


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


def _direct(root, manager: str, child: str) -> list:
    return [c for m in root.findall(manager) for c in m if c.tag == child]


def _one(items: list, what: str):
    if len(items) != 1:
        raise PageError(f"tables.xml: expected one {what}, found {len(items)}")
    return items[0]


def facts(raw: bytes, root) -> dict:
    """Everything the page says about the file, worked out from it."""
    f: dict = {}
    jv = root.find("jmriversion")
    if jv is None:
        raise PageError("tables.xml: no <jmriversion>")
    ver = f"{jv.findtext('major')}.{jv.findtext('minor')}"
    if (jv.findtext("test") or "0") != "0":
        ver += f".{jv.findtext('test')}"
    if (jv.findtext("modifier") or "").strip():
        ver += jv.findtext("modifier").strip()
    f["version"] = ver
    f["bytes"] = len(raw)
    f["lines"] = raw.count(b"\n") + (0 if raw.endswith(b"\n") else 1)
    secs = _sections(raw)
    if len(secs) != len(list(root)):
        raise PageError(f"tables.xml: found {len(secs)} sections by text but {len(list(root))} by XML")
    f["top"] = len(secs)
    total = sum(n for _, n, _ in secs)
    share = collections.Counter()
    rows: list[dict] = []
    for tag, n, name in secs:
        if tag not in GROUPS:
            raise PageError(f"tables.xml has a top-level <{tag}> the page does not describe; add it to GROUPS in {Path(__file__).name}")
        group, label, note = GROUPS[tag]
        share[group] += n / total
        if group == "panels":
            if name not in PANELS:
                raise PageError(f"tables.xml has a panel {name!r} the page does not describe; add it to PANELS in {Path(__file__).name}")
            label, note = name, PANELS[name]
        if rows and rows[-1]["group"] == group and rows[-1]["label"] == label:
            rows[-1]["share"] += n / total
            continue
        rows.append({"group": group, "label": label, "note": note, "share": n / total, "tag": tag})
    f["rows"], f["share"] = rows, dict(share)
    f["panels"] = sum(1 for r in rows if r["group"] == "panels")
    biggest = max(rows, key=lambda r: r["share"])
    f["largest"] = (biggest["label"], biggest["share"])

    # Blocks, layout blocks and the detectors they share.
    blocks = [b for b in _direct(root, "blocks", "block") if len(b) > 2]
    names = {b.findtext("systemName"): b.findtext("userName") or b.findtext("systemName") for b in blocks}
    lbs = _direct(root, "layoutblocks", "layoutblock")
    # A layout block may name its sensor by system or user name; count each sensor once.
    sensor_user = {e.findtext("systemName"): e.findtext("userName") or e.findtext("systemName")
                   for e in _direct(root, "sensors", "sensor")}
    users = collections.defaultdict(list)
    for lb in lbs:
        occ = lb.get("occupancysensor") or ""
        users[sensor_user.get(occ, occ)].append(lb.findtext("userName") or lb.findtext("systemName"))
    users.pop("", None)
    f["blocks"], f["layoutBlocks"], f["detectors"] = len(blocks), len(lbs), len(users)
    f["paths"] = sum(len(b.findall("path")) for b in blocks)
    shared = {d: u for d, u in users.items() if len(u) > 1}
    f["sharedCount"] = len(shared)
    f["sharedExamples"] = []
    for d in EXAMPLE_DETECTORS:
        if d not in shared:
            raise PageError(f"tables.xml: detector {d!r} is no longer shared by several layout blocks; pick another in EXAMPLE_DETECTORS")
        f["sharedExamples"].append((d, shared[d]))  # file order: Track S-1, then its West and East halves

    # The example sensor, block, Signal Mast Logic and turnout.
    s = _one([e for e in _direct(root, "sensors", "sensor") if e.findtext("userName") == EXAMPLE_SENSOR],
             f"sensor named {EXAMPLE_SENSOR!r}")
    f["sensor"] = (s.findtext("systemName"), EXAMPLE_SENSOR, (s.findtext("comment") or "").strip())
    if not f["sensor"][2]:
        raise PageError(f"tables.xml: sensor {EXAMPLE_SENSOR!r} has no comment, and the page quotes it")

    b = _one([e for e in blocks if e.findtext("userName") == EXAMPLE_BLOCK], f"block named {EXAMPLE_BLOCK!r}")
    legs = {}
    for p in b.findall("path"):
        for bs in p.findall("beansetting"):
            t = bs.find("turnout")
            if t is not None and t.get("systemName") == EXAMPLE_BLOCK_TURNOUT:
                legs.setdefault(SETTINGS.get(bs.get("setting"), bs.get("setting")), []).append(names.get(p.get("block"), p.get("block")))
    if sorted(legs) != ["Closed", "Thrown"] or any(len(v) != 1 for v in legs.values()):
        raise PageError(f"tables.xml: block {EXAMPLE_BLOCK!r} no longer has one closed and one thrown path through {EXAMPLE_BLOCK_TURNOUT!r}: {legs}")
    f["block"] = {"name": EXAMPLE_BLOCK, "sensor": b.findtext("occupancysensor") or "", "turnout": EXAMPLE_BLOCK_TURNOUT,
                  "closed": legs["Closed"][0], "thrown": legs["Thrown"][0], "more": len(b.findall("path")) > 2}
    if not f["block"]["sensor"]:
        raise PageError(f"tables.xml: block {EXAMPLE_BLOCK!r} has no occupancy sensor")

    src, dst = EXAMPLE_SML
    sml = _one([e for e in _direct(root, "signalmastlogics", "signalmastlogic") if e.findtext("sourceSignalMast") == src],
               f"Signal Mast Logic from {src!r}")
    d = _one([x for x in sml.findall("destinationMast") if x.findtext("destinationSignalMast") == dst],
             f"Signal Mast Logic destination {src!r} to {dst!r}")
    keys = ("enabled", "useLayoutEditor", "useLayoutEditorTurnouts", "useLayoutEditorBlocks", "associatedSection")
    f["sml"] = {"src": src, "dst": dst, **{k: (d.findtext(k) or "").strip() for k in keys}}
    if f["sml"]["associatedSection"] not in {e.findtext("systemName") for e in _direct(root, "sections", "section")} | \
            {e.findtext("userName") for e in _direct(root, "sections", "section")}:
        raise PageError(f"tables.xml: section {f['sml']['associatedSection']!r} named by {src} to {dst} does not exist")

    t = _one([e for e in _direct(root, "turnouts", "turnout") if e.findtext("userName") == EXAMPLE_TURNOUT],
             f"turnout named {EXAMPLE_TURNOUT!r}")
    if t.get("feedback") != "TWOSENSOR" or not (t.get("sensor1") and t.get("sensor2")):
        raise PageError(f"tables.xml: turnout {EXAMPLE_TURNOUT!r} no longer reports through two sensors, as the page says")
    f["turnout"] = (EXAMPLE_TURNOUT, t.get("sensor1"), t.get("sensor2"))

    ctc = root.find("ctcdata")
    f["ctcColumns"] = len(ctc.findall("ctcCodeButtonData")) if ctc is not None else 0
    f["logix"] = len(_direct(root, "logixs", "logix"))

    # The one LogixNG, its ConditionalNGs and their single actions.
    ng = _one(_direct(root, "LogixNGs", "LogixNG"), "LogixNG")
    ng_sys = ng.findtext("systemName")
    init = [x.text for m in root.findall("LogixNGs") for it in m.findall("InitializationTable") for x in it.findall("LogixNG")]
    if ng_sys not in init:
        raise PageError(f"tables.xml: LogixNG {ng_sys} is not in the Initialization Table, as the page says")
    cng = {c.findtext("systemName"): c for c in _direct(root, "LogixNGConditionalNGs", "ConditionalNG")}
    acts = {a.findtext("systemName"): a for m in root.findall("LogixNGDigitalActions") for a in m}
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
    if not rows or not rows[-1][3]:
        raise PageError("tables.xml: the last ConditionalNG no longer runs a script, as the page says")
    f["logixng"] = {"name": ng.findtext("userName") or ng_sys, "rows": rows}
    return f


def _xml(lines: list[str]) -> str:
    return html.escape("\n".join(lines), quote=False)


def regions(f: dict) -> dict[str, str]:
    """Each region's HTML."""
    e = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    obj, pan = f["share"].get("objects", 0), f["share"].get("panels", 0)
    x, rects, texts = BAR_X, [], []
    for cls, label, share, tcls in (("own", "Objects", obj, "t-b t-w"), ("acc", "Panels", pan, "t-b t-d")):
        w = round(BAR_W * share)
        rects.append(f'<rect class="{cls}" x="{x}" y="14" width="{w}" height="34" rx="3"/>')
        texts.append(f'<text class="{tcls}" x="{x + w // 2}" y="36" text-anchor="middle">{label}</text>')
        x += w
    rects.append(f'<rect class="own" x="{x}" y="14" width="{max(1, BAR_X + BAR_W - x)}" height="34" rx="3" '
                 'style="fill:var(--muted);stroke:var(--muted)"/>')
    bar = "\n          ".join(rects + texts)

    body, group = [], None
    for r in f["rows"]:
        if r["group"] != group:
            group = r["group"]
            body.append(f'<tr><td colspan="3"><strong>{GROUP_HEADS[group]}</strong></td></tr>')
        note = r["note"] if r["note"] is not None else f"{word(f['logix']).capitalize()} older-style logic items."
        body.append(f'<tr><td>{e(r["label"])}</td><td>{note}</td><td class="num">{pct(r["share"])}</td></tr>')
    sections = "\n            ".join(body)

    ex = [f'"{e(d)}" serves {e(and_list(u))}' for d, u in f["sharedExamples"]]
    shared = f"{word(f['sharedCount']).capitalize()} detectors are shared. {', and '.join(ex)}."

    blk = f["block"]
    bx = ["<block>", f"  <userName>{blk['name']}</userName>", f"  <occupancysensor>{blk['sensor']}</occupancysensor>"]
    for leg in ("Closed", "Thrown"):
        bx += [f'  <path block="{blk[leg.lower()]}">', f'    <beansetting setting="{leg}">',
               f"      <turnout>{blk['turnout']}</turnout>", "    </beansetting>", "  </path>"]
    bx += (["  ..."] if blk["more"] else []) + ["</block>"]

    s = f["sml"]
    sx = [f'<signalmastlogic source="{s["src"]}">', f'  <destinationMast destination="{s["dst"]}">']
    sx += [f"    <{k}>{s[k]}</{k}>" for k in ("enabled", "useLayoutEditor", "useLayoutEditorTurnouts",
                                           "useLayoutEditorBlocks", "associatedSection")]
    sx += ["  </destinationMast>", "</signalmastlogic>"]

    name, s1, s2 = f["turnout"]
    tx = ['<turnout feedback="TWOSENSOR"', f'         sensor1="{s1}"', f'         sensor2="{s2}">',
          f"  <userName>{name}</userName>", "</turnout>"]

    ng_rows = "\n            ".join(
        f"<tr><td>{e(n)}</td><td>{e(kind)}: {e(what)}{f'<code>{e(code)}</code>' if code else ''}</td></tr>"
        for n, kind, what, code in f["logixng"]["rows"])

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
        "panel-count": word(f["panels"]),
        "bar": bar,
        "largest": e(f["largest"][0]),
        "largest-share": pct(f["largest"][1]),
        "sections": sections,
        "layout-blocks": str(f["layoutBlocks"]),
        "detectors": str(f["detectors"]),
        "shared": shared,
        "block-name": e(blk["name"]),
        "block-sensor": e(blk["sensor"]),
        "block-xml": _xml(bx),
        "block-sentence": (f"from {e(blk['name'])} you can go to {e(blk['closed'])} when {e(blk['turnout'])} is closed, "
                           f"and to {e(blk['thrown'])} when it is thrown"),
        "paths": f"{f['paths']:,}",
        "sml-xml": _xml(sx),
        "sml-section": e(s["associatedSection"]),
        "turnout-xml": _xml(tx),
        "ctc-columns": str(f["ctcColumns"]),
        "logixng-name": e(f["logixng"]["name"]),
        "logixng-count": word(len(f["logixng"]["rows"])),
        "logixng-rows": ng_rows,
    }


def fill(page: str, f: dict) -> str:
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
