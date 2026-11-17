#!/usr/bin/env python3
"""Trial: the staging Layout Editor panel built from the staging device map alone, with no overlay (phase 1).

    python3 tools/schematic/build_staging_candidate.py            # write the trial, the diff report and the images
    python3 tools/schematic/build_staging_candidate.py --no-images
    python3 tools/schematic/build_staging_candidate.py --check    # fail if the staged boundaries file is stale

For the owner to review; nothing live reads it. It is the staging half of one input path for the Layout Editor
build: staging drawn the way main and upper are, from device_map_staging.csv, control_points_staging.csv and
staging_masts.csv (staging_device_map.py), not from the frozen hand-drawn panel (staging_le/, le_inputs.py) and not
with its hand-placed icons (overlay.json, le_overlay.py).

Writes, under jmri/layouts/hart/output/trial/ (gitignored, never the live tables.xml):
- tables_staging_devicemap.xml: the same tables build_layout_le.py --levels staging --as-live starts from (the last
  hand-drawn tables, hartlib.hand_drawn) with the "HART Railroad" panel replaced by this build's. Drawn at that
  candidate's grid (FIT, STRETCH, STAGING_ROW, the west shift, the crossover angle, NAME_COLUMNS), so the two can
  be laid over each other. The panel's attributes and drawing options are the replaced panel's own.
- staging_devicemap_diff.txt: beans, panels, turnouts, masts and overlay items of the trial against the current
  staging candidate, tables_cutover_staging.xml (build it first: build_layout_le.py --levels staging --as-live).
- staging_devicemap_trial.png, staging_devicemap_current.png and staging_devicemap_trial_parked_lamps.png: the
  panels drawn to scale (render_panel).
And, committed, jmri/layouts/hart/data/schematic/staged/le_signal_boundaries.csv (staged_boundaries): the mast
boundary contract with each mast at the ident and slot it has on this panel, for the cut-over (staged/README.md).

What the trial leaves to rules, and so differs on purpose (the diff report lists each):
- Turnout idents come from switches.csv (le_ident); anchors, end bumpers and track segments take generated idents
  (owner, 2026-11-17: accepted).
- A turnout's normal leg is its closed leg in switch_legs.csv; Layout Editor leg B is the plugin's default (the
  drawn straight leg), which gives every staging turnout its live leg letters and type.
- Masts go in the slot the plugin finds for their facing and protected blocks and kind (staging_masts.csv);
  check_masts below stops on a mast that would fit two slots or stands on another turnout than its switch's.
- The panel's own items come from panel_items.json (panel_items.py): the status cluster panel_status.py drives, the
  frame captions, the helix destination labels and the backdrop. The occupancy lamps and the station clusters are
  parked with the Dispatcher System (jmri/layouts/hart/parked/staging_panel_lamps.json); the run also builds a copy
  with them put back (staging_devicemap_trial_parked_lamps.png) and the report says how many land where they were.
  No Entry/Exit sensors (Entry/Exit is parked).
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import csv
import io
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_layout_le as blb  # noqa: E402  the staging candidate's drawing settings and helpers (read only)
import panel_items  # noqa: E402  the panel's fixed items (panel_items.json)
import publish_draft as pd  # noqa: E402  the plugin cache
import staging_device_map as sdm  # noqa: E402  the staging device map and its reader
from hartlib import paths, tables  # noqa: E402

TRIAL_DIR = paths.LAYOUT_OUTPUT / "trial"
OUT = TRIAL_DIR / "tables_staging_devicemap.xml"
REPORT = TRIAL_DIR / "staging_devicemap_diff.txt"
IMAGES = {"trial": TRIAL_DIR / "staging_devicemap_trial.png", "current": TRIAL_DIR / "staging_devicemap_current.png",
          "lamps": TRIAL_DIR / "staging_devicemap_trial_parked_lamps.png"}
REFERENCE = blb.CUTOVER_STAGING
PANEL = blb.TEMPLATE_PANEL
ITEMS = pd.DATA / "panel_items.json"
PARKED_LAMPS = paths.LAYOUT_DATA.parent / "parked" / "staging_panel_lamps.json"
BOUNDARIES = paths.LAYOUT_DATA / "le_signal_boundaries.csv"
STAGED_BOUNDARIES = pd.DATA / "staged" / "le_signal_boundaries.csv"
ITEM_TAGS = ("sensoricon", "positionablelabel", "signalheadicon", "turnouticon", "BlockContentsIcon",
             "signalmasticon", "memoryicon")


class CandidateError(RuntimeError):
    pass


# ---------------------------------------------------------------- the build

def staging_bands():
    """([the staging band as the candidate draws it], page options)."""
    bands, page = blb.schematic()
    bands = blb.straights_lengthened(blb.west_shifted(bands))
    keys = [blb.band_key(t) for t, _b, _o in bands]
    if blb.STAGING not in keys:
        raise CandidateError(f"no {blb.STAGING} band in the schematic (bands: {', '.join(keys)})")
    return [bands[keys.index(blb.STAGING)]], page


def check_masts(P, names: dict, le_mod) -> None:
    """Stop when a staging mast fits more than one slot of its kind with its blocks (the plugin would take the first,
    a guess), or a turnout mast stands on another turnout than its switch's (staging_masts.csv `switch`)."""
    ix = blb.slots_module().Index(le_mod.to_xml(P, "check"))
    fits = defaultdict(list)
    for c in ix.candidates():
        f, pr = ix.blocks(*c)
        fits[(c[0], f, tuple(pr))].append(c)
    rows = {r["mast"]: r for r in sdm.read_rows(sdm.MASTS, sdm.level_masts.FIELDS)}
    turnout_of = {r["trial_name"].removeprefix("Switch "): r["jmri_name"]
                  for r in sdm.read_rows(sdm.DEVICE_MAP, sdm.bdm.COLUMNS)
                  if r["layer"] == "turnout" and r["trial_name"]}
    placed = {m["mast"]: m for m in ix.masts()}
    bad = []
    for m in names["masts"]:
        got = placed.get(m["mast"])
        if got is None:
            bad.append(f"{m['mast']} is not on the panel")
            continue
        same = fits[(got["kind"], got["facing"], tuple(got["protects"]))]
        if m["kind"] == "turnout":
            want = turnout_of.get(rows[m["mast"]]["switch"])
            if got.get("turnout") != want:
                bad.append(f"{m['mast']} is on turnout {got.get('turnout')}, its switch's is {want}")
            same = [c for c in same if ix.turnouts[c[1]].get("turnoutname") == want]
        if len(same) > 1:
            bad.append(f"{m['mast']} fits {len(same)} slots ({', '.join(f'{c[1]} {c[2]}' for c in same)})")
    if bad:
        raise CandidateError("staging masts not placed for certain: " + "; ".join(bad))


def build(base: Path, parked_lamps: bool = False):
    """(tables bytes, the plugin's Panel, names). Stops on any name the base tables do not have. `parked_lamps`: also
    put the parked lamps and station clusters on (PARKED_LAMPS), to check they come back where they were."""
    _sheet, le_mod, core = blb.plugin()
    bands, page = staging_bands()
    band, opts = bands[0][1], bands[0][2]
    doc = tables.load(base)
    root = doc.root
    old = tables.layout_editor(root, PANEL)
    if old is None:
        raise CandidateError(f"{paths.rel(base)} has no {PANEL!r} panel to replace")
    names = {blb.STAGING: sdm.load(band)}
    names[blb.STAGING]["lengths"] = blb.staging_lengths(opts, names[blb.STAGING])
    if "le_labels" in page:
        raise CandidateError("the schematic's page options already hold le_labels; HART sets them (LE_LABELS)")
    page = dict(page, le_labels=dict(blb.LE_LABELS))
    try:
        fitted = le_mod.panel(bands, names, page=page, fit=blb.FIT, row=blb.STAGING_ROW).scale
        scale = (fitted[0] * blb.STRETCH, fitted[1])
        P = le_mod.panel(blb.staging_columns(bands), names, cell=le_mod.CELL * scale[0], row=blb.STAGING_ROW * scale[1],
                         page=page, crossover_run={blb.STAGING: blb.crossover_run(scale)[blb.STAGING]})
    except core.SchematicError as exc:
        raise CandidateError(f"schematic le: {exc}") from None
    P.scale = scale
    blb.check_unplaced(P)
    check_masts(P, names[blb.STAGING], le_mod)
    nm = names[blb.STAGING]
    live_turnouts = tables.by_any_name(tables.turnouts(root))
    live_lb = {tables.user_name(b) for b in tables.layout_blocks(root)}
    masts = tables.mast_system_names(root)
    missing = sorted(t for t in set(nm["turnouts"].values()) if t not in live_turnouts) + \
        sorted(b for b in set(P.blocks) if b not in live_lb) + \
        sorted(m["mast"] for m in nm["masts"] if m["mast"] not in masts)
    if missing:
        raise CandidateError(f"names the base tables do not have: {missing}")
    attrs = dict(old.attrib)
    panel_el = le_mod.to_xml(P, PANEL, attrs, copy.deepcopy(old.find("layoutTrackDrawingOptions")))
    try:
        items = panel_items.load(ITEMS)
        if items["panel"] != PANEL:
            raise CandidateError(f"{paths.rel(ITEMS)} is for panel {items['panel']!r}, not {PANEL!r}")
        P.items_placed = panel_items.place(panel_el, items, le_mod, blb.slots_module(), blb.FIT, le_mod.CHROME)
        if parked_lamps:
            P.items_placed += panel_items.place(panel_el, panel_items.load(PARKED_LAMPS), le_mod,
                                                blb.slots_module(), blb.FIT, le_mod.CHROME)
    except panel_items.ItemsError as exc:
        raise CandidateError(f"panel items: {exc}") from None
    # a panel larger than its window scrolls both ways (as build_layout_le.py's cut-over candidate)
    w, h = float(panel_el.get("panelwidth")), float(panel_el.get("panelheight"))
    if w + le_mod.CHROME[0] > blb.FIT[0] or h + le_mod.CHROME[1] > blb.FIT[1]:
        panel_el.set("scrollable", "both")
    opts_el = panel_el.find("layoutTrackDrawingOptions")
    panel_el.insert(list(panel_el).index(opts_el) + 1 if opts_el is not None else 0, tables.generated_marker_label())
    blb.replace(root, old, panel_el, 1)
    return doc.tobytes(), P, names


# ---------------------------------------------------------------- the boundary contract, staged for the cut-over

def staged_boundaries(panel: ET.Element, path: Path = BOUNDARIES) -> str:
    """le_signal_boundaries.csv as it must read once this panel is live: each mast row at the ident the mast has on
    `panel` (anchor idents are generated), every other column as it is. Stops when a mast is not on the panel, is
    in another kind of slot, or stands in another slot than its row gives (its generated_slot where it has one,
    tables.boundary_slot), or a turnout mast on another turnout: only anchor idents may change."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns, rows = reader.fieldnames, list(reader)
    placed = {m["mast"]: m for m in blb.slots_module().Index(panel).masts()}
    bad = []
    for r in rows:
        m = placed.get(r["mast_user_name"])
        if m is None:
            bad.append(f"{r['mast_user_name']} is not on the panel")
            continue
        if m["kind"] != r["kind"]:
            bad.append(f"{r['mast_user_name']} is in a {m['kind']} slot, its row says {r['kind']}")
            continue
        slot = tables.boundary_slot(r, generated=True)
        if m["slot"] != slot or (r["kind"] == "turnout" and m["ident"] != r["ident"]):
            bad.append(f"{r['mast_user_name']} stands at {m['ident']} {m['slot']}, its row gives {r['ident']} {slot}")
            continue
        r["ident"] = m["ident"]
    if bad:
        raise CandidateError(f"{paths.rel(path)} cannot follow this panel: " + "; ".join(bad))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def item_places(panel) -> dict:
    """{(tag, what it shows): sorted [(x, y)]} of a panel's icons and labels."""
    out = defaultdict(list)
    for el in panel_items_of(panel):
        out[item_key(el)].append((round(float(el.get("x"))), round(float(el.get("y")))))
    return {k: sorted(v) for k, v in out.items()}


def panel_items_of(panel) -> list[ET.Element]:
    return [el for el in panel if el.tag in ITEM_TAGS and el.get("x") is not None]


def compare_items(path: Path, trial_places: dict, ref_places: dict) -> tuple[int, int, list[str]]:
    """(at the same place within 1 px, all, [how the others differ]) of the elements of an items file."""
    same, total, off = 0, 0, []
    for it in panel_items.load(path)["items"]:
        for m in it.get("members") or [it]:
            k = item_key(ET.fromstring(m["xml"]))
            total += 1
            t, r = trial_places.get(k, []), ref_places.get(k, [])
            if any(any(abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1 for b in r) for a in t):
                same += 1
            else:
                off.append(f"{it['id']}: trial {t or 'none'}, current {r or 'none'}")
    return same, total, off


# ---------------------------------------------------------------- the diff report

def section_beans(root) -> dict:
    """{(section tag, bean tag, key): canonical text} of every bean outside the Layout Editor panels."""
    out = {}
    for sec in root:
        if sec.tag == "LayoutEditor":
            continue
        for i, el in enumerate(sec):
            key = tables.system_name(el) or el.get("systemName") or el.get("name") or f"#{i}"
            out[(sec.tag, el.tag, key)] = blb.canon(el)
    return out


def item_key(el) -> tuple:
    """What an icon or label shows: its tag and the bean or text it names."""
    name = (el.get("sensor") or el.get("blockcontents") or el.get("turnout") or el.get("signalhead") or
            el.get("signalmast") or el.get("text") or (el.find("icon").get("url") if el.find("icon") is not None
                                                      else "") or "?")
    return el.tag, name


def diff(trial_root, ref_root, le_mod, overlay: dict, lamps_root=None) -> list[str]:
    """The diff report's lines. `lamps_root`: the trial built with the parked lamps put back, whose places are
    compared with the current candidate's."""
    lines = []
    tb, rb = section_beans(trial_root), section_beans(ref_root)
    same = sum(1 for k in tb if k in rb and tb[k] == rb[k])
    changed = sorted(k for k in tb if k in rb and tb[k] != rb[k])
    lines.append("== Beans (every table outside the Layout Editor panels)")
    lines.append(f"identical: {same}; differ: {len(changed)}; only in trial: {len(set(tb) - set(rb))}; "
                 f"only in current: {len(set(rb) - set(tb))}")
    lines += [f"  differs: {k}" for k in changed[:40]]
    lines += [f"  only in trial: {k}" for k in sorted(set(tb) - set(rb))[:40]]
    lines += [f"  only in current: {k}" for k in sorted(set(rb) - set(tb))[:40]]

    tp, rp = tables.layout_editors(trial_root), tables.layout_editors(ref_root)
    others = [(a.get("name"), blb.canon(a) == blb.canon(b)) for a, b in zip(tp, rp) if a.get("name") != PANEL]
    lines.append("")
    lines.append("== Other Layout Editor panels")
    lines += [f"  {n}: {'identical' if ok else 'DIFFERS'}" for n, ok in others] or ["  none"]

    t, r = tables.layout_editor(trial_root, PANEL), tables.layout_editor(ref_root, PANEL)
    lines.append("")
    lines.append(f"== Panel {PANEL!r}")
    diffs_attr = sorted(k for k in set(t.attrib) | set(r.attrib) if t.get(k) != r.get(k))
    lines.append("attributes that differ: " + (", ".join(f"{k} {r.get(k)} -> {t.get(k)}" for k in diffs_attr)
                                               or "none"))
    count = lambda p: Counter(el.tag for el in p)         # noqa: E731
    tc, rc = count(t), count(r)
    lines.append("elements (current -> trial): " + ", ".join(f"{k} {rc.get(k, 0)} -> {tc.get(k, 0)}"
                                                             for k in sorted(set(tc) | set(rc))))
    # turnouts, by the turnout they bind
    tf = {f["name"]: dict(f, ident=i) for i, f in blb.turnout_facts(t).items()}
    rf = {f["name"]: dict(f, ident=i) for i, f in blb.turnout_facts(r).items()}
    lines.append("")
    lines.append("-- Layout Editor turnouts (by turnout name)")
    ident_same = sum(1 for n in tf if n in rf and tf[n] == rf[n])
    lines.append(f"identical in ident, type, continuing route, leg blocks and the block on each leg: {ident_same} "
                 f"of {len(rf)}")
    for n in sorted(set(tf) | set(rf), key=sdm.bdm.natural):
        a, b = rf.get(n), tf.get(n)
        if a is None or b is None:
            lines.append(f"  {n}: only in {'trial' if a is None else 'current'}")
            continue
        d = [f"{k} {a[k]} -> {b[k]}" for k in a if a[k] != b[k]]
        if d:
            lines.append(f"  {n}: " + "; ".join(d))
    geo = ("xcen", "ycen", "xb", "yb", "xc", "yc")
    where = lambda p: {el.get("turnoutname"): tuple(el.get(a) for a in geo)  # noqa: E731
                       for el in p.findall("layoutturnout")}
    tg, rg = where(t), where(r)
    moved_t = sorted((n for n in rg if tg.get(n) != rg[n]), key=sdm.bdm.natural)
    lines.append(f"turnouts drawn at the same centre and legs: {len(rg) - len(moved_t)} of {len(rg)}"
                 + (f"; moved: {', '.join(moved_t)}" if moved_t else ""))
    pts = lambda p: sorted((el.get("type"), el.get("x"), el.get("y")) for el in p.findall("positionablepoint"))  # noqa
    lines.append(f"anchors and end bumpers at the same places: {'yes' if pts(t) == pts(r) else 'NO'}")
    # masts, by where JMRI resolves them
    ix = blb.slots_module().Index
    tm = {m["mast"]: m for m in ix(t).masts()}
    rm = {m["mast"]: m for m in ix(r).masts()}
    lines.append("")
    lines.append("-- Signal masts (slot kind, facing block, protected blocks, turnout)")
    key = lambda m: (m["kind"], m["facing"], tuple(m["protects"]), m.get("turnout"))     # noqa: E731
    at = lambda m: (m["ident"], m["slot"])      # noqa: E731
    lines.append(f"resolving the same: {sum(1 for n in tm if n in rm and key(tm[n]) == key(rm[n]))} of {len(rm)}; "
                 f"same ident and slot too: {sum(1 for n in tm if n in rm and at(tm[n]) == at(rm[n]))}")
    for n in sorted(set(tm) | set(rm), key=sdm.bdm.natural):
        a, b = rm.get(n), tm.get(n)
        if a is None or b is None:
            lines.append(f"  {n}: only in {'trial' if a is None else 'current'}")
        elif key(a) != key(b):
            lines.append(f"  {n}: current {key(a)} at {a['ident']} {a['slot']}, trial {key(b)} at {b['ident']} "
                         f"{b['slot']}")
    moved = sorted(n for n in tm if n in rm and (tm[n]["ident"], tm[n]["slot"]) != (rm[n]["ident"], rm[n]["slot"]))
    lines.append(f"masts in another ident or slot (generated anchor idents, plugin leg letters): {len(moved)}: "
                 + ", ".join(f"{n} {rm[n]['ident']} {rm[n]['slot']} -> {tm[n]['ident']} {tm[n]['slot']}"
                             for n in moved))
    # Entry/Exit sensors in slots
    nx = lambda p: sum(1 for el in p.iter() if (el.tag.startswith("sensor") and el.tag[-1:] in "ABCD" and  # noqa
                                                 el.tag != "sensoricon") or any(k.endswith("boundsensor")
                                                                                for k in el.attrib))
    lines.append("")
    lines.append(f"-- Entry/Exit sensors bound in slots: current {nx(r)}, trial {nx(t)} (Entry/Exit is parked)")
    # blocks drawn
    blocks_of = lambda p: {s.get("blockname") for s in p.findall("tracksegment") if s.get("blockname")} | \
        {t.get(a) for t in p.findall("layoutturnout") for a in ("blockname", "blockbname", "blockcname",  # noqa
                                                                 "blockdname") if t.get(a)}
    bt, br = blocks_of(t), blocks_of(r)
    lines.append(f"-- Blocks drawn: current {len(br)}, trial {len(bt)}; only current: {sorted(br - bt) or 'none'}; "
                 f"only trial: {sorted(bt - br) or 'none'}")
    # icons and labels
    lines.append("")
    lines.append("-- Icons and labels (by what they show)")
    ti, ri = Counter(item_key(e) for e in panel_items_of(t)), Counter(item_key(e) for e in panel_items_of(r))
    for tag in sorted({k[0] for k in ti} | {k[0] for k in ri}):
        a = sum(v for k, v in ri.items() if k[0] == tag)
        b = sum(v for k, v in ti.items() if k[0] == tag)
        lines.append(f"  {tag}: current {a}, trial {b}")
    tg_, rg_ = item_places(t), item_places(r)
    for tag in ("BlockContentsIcon", "signalmasticon"):
        keys = [k for k in rg_ if k[0] == tag]
        moved_k = sorted(k[1] for k in keys if tg_.get(k) != rg_[k])
        lines.append(f"  {tag} places: {len(keys) - len(moved_k)} of {len(keys)} the same"
                     + (f"; placed elsewhere by the label layer (no station clusters to keep clear of): "
                        f"{', '.join(moved_k)}" if moved_k else ""))
    # the overlay's items
    lines.append("")
    lines.append("== overlay.json items (the hand-placed icons the current candidate carries)")
    keys_in = lambda path: {item_key(ET.fromstring(m["xml"])) for it in panel_items.load(path)["items"]  # noqa
                            for m in it.get("members") or [it]}
    fixed, parked = keys_in(ITEMS), keys_in(PARKED_LAMPS)
    groups = defaultdict(list)
    for it in overlay["items"]:
        el = ET.fromstring(it["xml"])
        k = item_key(el)
        kind = it.get("group") or ((it.get("anchor") or {}).get("kind") if isinstance(it.get("anchor"), dict)
                                   else None) or "free"
        station = str(kind).startswith("station")
        fate = ("parked (staging_panel_lamps.json)" if station and k in parked else
                "panel_items.json" if k in fixed and ti.get(k) else
                "parked (staging_panel_lamps.json)" if k in parked else "lost")
        groups[(fate, el.tag, str(kind).split(" ")[0])].append(k[1])
    for (fate, tag, kind), items in sorted(groups.items()):
        lines.append(f"  {fate}: {len(items)} {tag} ({kind}): {', '.join(sorted(set(items), key=sdm.bdm.natural))}")
    rp = item_places(r)
    checks = [("panel_items.json", ITEMS, t)]
    if lamps_root is not None:
        checks.append(("parked lamps and stations, put back on a copy of the trial", PARKED_LAMPS,
                       tables.layout_editor(lamps_root, PANEL)))
    for what, path, panel in checks:
        same_n, total, off = compare_items(path, item_places(panel), rp)
        lines.append(f"  {what}: {same_n} of {total} elements where the current candidate has them (within 1 px)")
        lines += [f"    differs: {o}" for o in off]
    lines.append(f"  panel size: current {r.get('panelwidth')}x{r.get('panelheight')}, trial "
                 f"{t.get('panelwidth')}x{t.get('panelheight')} px; window current {r.get('windowwidth')}x"
                 f"{r.get('windowheight')}, trial {t.get('windowwidth')}x{t.get('windowheight')}")
    lines.append("  generated by the plugin in both builds (overlay.json 'dropped', given): " + "; ".join(
        f"{len(v)} {k.replace('_', ' ')}" for k, v in overlay["dropped"].items() if k in ("block_contents",
                                                                                           "switch_numbers",
                                                                                           "track_names",
                                                                                           "captions")))
    lines.append("  left out of both (overlay.json 'dropped', not carried): " + "; ".join(
        f"{len(v)} {k.replace('_', ' ')}" for k, v in overlay["dropped"].items() if k in ("nx_icons",
                                                                                           "ladder_buttons")))
    return lines


# ---------------------------------------------------------------- the images

def render_panel(panel, le_mod, out: Path, title: str, scale: float = 1.0) -> None:
    """A PNG of a Layout Editor panel to scale: track by block (hidden segments dashed grey), turnouts with their
    block colour, mast icons as red triangles, sensor and other icons as their boxes, labels and block contents
    as their text. Not JMRI's own drawing: for laying two panels side by side."""
    from PIL import Image, ImageDraw, ImageFont
    import le_overlay        # its Track reads a panel's drawn pieces per block (read only)
    track = le_overlay.Track(panel, le_mod, blb.slots_module(), title)
    x0, y0, x1, y1 = track.box
    items = panel_items_of(panel)
    xs = [float(e.get("x") or 0) for e in items] + [x1]
    ys = [float(e.get("y") or 0) for e in items] + [y1]
    W, H = int((max(xs) + 60) * scale), int((max(ys) + 60) * scale) + 24
    img = Image.new("RGB", (W, H), (236, 240, 246))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", max(9, int(10 * scale)))
    except OSError:
        font = ImageFont.load_default()
    dr.text((6, 4), title, fill=(0, 0, 0), font=font)
    off = 24
    P = lambda p: (p[0] * scale, p[1] * scale + off)     # noqa: E731
    palette = [(40, 40, 40), (25, 90, 160), (150, 70, 20), (20, 120, 60), (120, 40, 120)]
    for i, (block, pcs) in enumerate(sorted(track.pieces.items())):
        col = palette[i % len(palette)]
        for a, b in pcs:
            dr.line([P(a), P(b)], fill=col, width=max(2, int(3 * scale)))
    for t in panel.findall("layoutturnout"):
        c = (float(t.get("xcen")), float(t.get("ycen")))
        r = 4 * scale
        dr.ellipse([P(c)[0] - r, P(c)[1] - r, P(c)[0] + r, P(c)[1] + r], outline=(0, 140, 0), width=2)
    for e in items:
        x, y = float(e.get("x") or 0), float(e.get("y") or 0)
        p = P((x, y))
        if e.tag == "signalmasticon":
            if e.get("hidden") == "yes":
                dr.polygon([p, (p[0] + 8 * scale, p[1]), (p[0] + 4 * scale, p[1] + 10 * scale)], outline=(200, 0, 0))
            else:
                dr.polygon([p, (p[0] + 8 * scale, p[1]), (p[0] + 4 * scale, p[1] + 10 * scale)], fill=(200, 0, 0))
        elif e.tag in ("positionablelabel", "BlockContentsIcon") and (e.get("text") or e.get("blockcontents")):
            text = e.get("text") or ("[" + e.get("blockcontents") + "]")
            if e.get("hidden") == "yes" or text.startswith("GENERATED"):
                continue
            dr.text(p, text, fill=(0, 0, 120) if e.tag == "positionablelabel" else (110, 110, 110), font=font)
        elif e.tag == "positionablelabel":
            continue        # a backdrop image
        else:
            s = 10 * scale
            col = (0, 150, 150) if e.tag == "sensoricon" else (160, 120, 0)
            dr.rectangle([p[0], p[1], p[0] + s, p[1] + s], outline=col, width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


# ---------------------------------------------------------------- the command

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-images", action="store_true", help="skip the two PNGs")
    ap.add_argument("--tables", type=Path, help="the tables to build on (default: build_layout_le.template_tables)")
    ap.add_argument("--check", action="store_true",
                    help=f"build in memory and fail if {paths.rel(STAGED_BOUNDARIES)} is stale; writes nothing")
    args = ap.parse_args(argv)
    if not args.check:
        message = paths.check_only_message(Path(__file__).name)
        if message:
            print(f"ERROR: {message}")
            return 1
        if blb.live_target(OUT):
            print(f"ERROR: {OUT} is the live tables or in the JMRI profile")
            return 1
        if not REFERENCE.exists():
            print(f"ERROR: {paths.rel(REFERENCE)} is missing: run python3 tools/schematic/build_layout_le.py "
                  "--levels staging --as-live first (the current staging candidate the trial is compared with)")
            return 1
    with contextlib.ExitStack() as stack:
        stack.enter_context(pd.cache_on())
        base = args.tables or blb.template_tables()
        try:
            data, P, _names = build(base)
            staged = staged_boundaries(tables.layout_editor(tables.loads(data).root, PANEL))
            lamps_data = None if args.check else build(base, parked_lamps=True)[0]
        except (CandidateError, sdm.StagingMapError, blb.BuildError) as exc:
            print(f"ERROR: {exc}")
            return 1
        if args.check:
            if not STAGED_BOUNDARIES.exists() or STAGED_BOUNDARIES.read_text(encoding="utf-8") != staged:
                print(f"STALE: {paths.rel(STAGED_BOUNDARIES)}; run {paths.rel(Path(__file__))}")
                return 1
            print(f"ok: {paths.rel(STAGED_BOUNDARIES)} current")
            return 0
        _, le_mod, _ = blb.plugin()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        tables.loads(data, path=OUT).save(OUT)
        print(f"wrote {paths.rel(OUT)}: {le_mod.summary(P)}; {P.items_placed} panel items")
        if not STAGED_BOUNDARIES.exists() or STAGED_BOUNDARIES.read_text(encoding="utf-8") != staged:
            STAGED_BOUNDARIES.parent.mkdir(parents=True, exist_ok=True)
            STAGED_BOUNDARIES.write_text(staged, encoding="utf-8")
            print(f"wrote {paths.rel(STAGED_BOUNDARIES)}")
        import le_inputs
        trial_root, ref_root = tables.loads(data).root, tables.read(REFERENCE)
        lamps_root = tables.loads(lamps_data).root
        lines = diff(trial_root, ref_root, le_mod, le_inputs.load().overlay, lamps_root)
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {paths.rel(REPORT)}")
        if not args.no_images:
            for which, root in (("trial", trial_root), ("current", ref_root), ("lamps", lamps_root)):
                panel = tables.layout_editor(root, PANEL)
                title = {"trial": f"{PANEL}: trial from the staging device map and panel_items.json",
                         "current": f"{PANEL}: current staging candidate (frozen inputs and overlay)",
                         "lamps": f"{PANEL}: the trial with the parked lamps and station clusters put back"}[which]
                render_panel(panel, le_mod, IMAGES[which], title)
                print(f"wrote {IMAGES[which]}")
    for line in P.log:
        print(f"  note: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
