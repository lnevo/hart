#!/usr/bin/env python3
"""The device-map staging candidates, built by build_layout_le.py --staging devicemap, set against the frozen ones.

    python3 tools/schematic/build_staging_candidate.py            # the staged file, the report and images
    python3 tools/schematic/build_staging_candidate.py --no-images
    python3 tools/schematic/build_staging_candidate.py --check    # fail if the staged boundaries file is stale

For the owner to review; nothing live reads it. build_layout_le.py draws staging from the staging device map
(device_map_staging.csv, control_points_staging.csv, staging_masts.csv; staging_device_map.py) and panel_items.json
when given `--staging devicemap` (its module text, "Staging from the device map"). This script reads the candidates
that build wrote (`build_layout_le.py --as-live --staging devicemap --review`; make panels runs it just before this
step) and sets each beside the frozen path's (`build_layout_le.py --as-live`); it builds nothing itself:

    staging alone   output/trial/tables_cutover_devicemap_staging.xml   against tables_cutover_staging.xml
    three levels    output/trial/tables_cutover_devicemap.xml           against tables_cutover.xml

It writes, under jmri/layouts/hart/output/trial/ (gitignored, never the live tables.xml):
- staging_devicemap_diff.txt: beans, panels, turnouts, masts, icons and the overlay's items, for each pair;
- staging_devicemap_trial.png, staging_devicemap_current.png and staging_devicemap_trial_parked_lamps.png: the
  staging panels drawn to scale (render_panel); the last with the parked lamps and station clusters put back on a
  copy (jmri/layouts/hart/parked/staging_panel_lamps.json), to check they come back where they were; and
  devicemap_three_levels.png, the three-level device-map candidate.
And, committed, jmri/layouts/hart/data/schematic/staged/le_signal_boundaries.csv (staged_boundaries): the mast
boundary contract with each mast at the ident and slot it has on the device-map panel, for the cut-over
(staged/README.md).
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_layout_le as blb  # noqa: E402  the build, its trial files and helpers
import panel_items  # noqa: E402  the panel's fixed items (panel_items.json)
import publish_draft as pd  # noqa: E402  the plugin cache
from hartlib import paths, railroad, tables  # noqa: E402

TRIAL_DIR = paths.LAYOUT_OUTPUT / "trial"
REPORT = TRIAL_DIR / "staging_devicemap_diff.txt"
IMAGES = {"trial": TRIAL_DIR / "staging_devicemap_trial.png", "current": TRIAL_DIR / "staging_devicemap_current.png",
          "lamps": TRIAL_DIR / "staging_devicemap_trial_parked_lamps.png",
          "all": TRIAL_DIR / "devicemap_three_levels.png"}
# (device-map candidate, the frozen one it is set against)
PAIRS = {"staging": (blb.default_out("staging", True, "devicemap"), blb.CUTOVER_STAGING),
         "all": (blb.default_out("all", True, "devicemap"), blb.CUTOVER)}
PANEL = blb.TEMPLATE_PANEL
ITEMS = blb.PANEL_ITEMS
PARKED_LAMPS = paths.LAYOUT_DATA.parent / "parked" / "staging_panel_lamps.json"
BOUNDARIES = paths.LAYOUT_DATA / "le_signal_boundaries.csv"
STAGED_BOUNDARIES = pd.DATA / "staged" / "le_signal_boundaries.csv"
ITEM_TAGS = panel_items.TAGS + ("BlockContentsIcon",)    # the items a panel file may hold, and the plugin's icons
natural = railroad.natural


class CandidateError(RuntimeError):
    pass


def with_parked_lamps(data: bytes, le_mod) -> ET.Element:
    """The tables `data` with the parked lamps and station clusters put back on the staging panel (a copy), tied to
    the staging track as panel_items.json's items are."""
    root = tables.loads(data).root
    panel = tables.layout_editor(root, PANEL)
    staging = {s.get("blockname") for s in panel.findall("tracksegment")} | \
        {t.get(a) for t in panel.findall("layoutturnout") for a in ("blockname", "blockbname", "blockcname",
                                                                    "blockdname")}
    try:
        panel_items.place(panel, panel_items.load(PARKED_LAMPS), le_mod, blb.slots_module(), blb.FIT,
                          le_mod.CHROME, frame_blocks=staging - {None, ""})
    except panel_items.ItemsError as exc:
        raise CandidateError(f"parked lamps: {exc}") from None
    return root


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

    by_name = lambda root: {p.get("name"): p for p in tables.layout_editors(root) if p.get("name") != PANEL}  # noqa
    tp, rp = by_name(trial_root), by_name(ref_root)
    lines.append("")
    lines.append("== Other Layout Editor panels (by name)")
    lines += [f"  {n}: " + ("only in trial" if n not in rp else "only in current" if n not in tp else
                            "identical" if blb.canon(tp[n]) == blb.canon(rp[n]) else "DIFFERS")
              for n in sorted(set(tp) | set(rp))] or ["  none"]

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
    for n in sorted(set(tf) | set(rf), key=natural):
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
    moved_t = sorted((n for n in rg if tg.get(n) != rg[n]), key=natural)
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
    for n in sorted(set(tm) | set(rm), key=natural):
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
    if overlay is None:
        return lines
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
        lines.append(f"  {fate}: {len(items)} {tag} ({kind}): {', '.join(sorted(set(items), key=natural))}")
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
    ap.add_argument("--no-images", action="store_true", help="skip the PNGs")
    ap.add_argument("--check", action="store_true",
                    help=f"fail if {paths.rel(STAGED_BOUNDARIES)} does not follow the device-map staging candidate; "
                         "writes nothing")
    args = ap.parse_args(argv)
    if not args.check:
        message = paths.check_only_message(Path(__file__).name)
        if message:
            print(f"ERROR: {message}")
            return 1
    # the candidates build_layout_le.py wrote (make panels: le-cutover and le-cutover-devicemap, just before this
    # step, whose --check holds them current): read, not built again
    need = [PAIRS["staging"][0]] if args.check else [p for pair in PAIRS.values() for p in pair]
    missing = [p for p in need if not p.exists()]
    if missing:
        print(f"ERROR: {', '.join(paths.rel(m) for m in missing)} missing: run python3 tools/schematic/"
              "build_layout_le.py --as-live, and with --staging devicemap --review, first")
        return 1
    built = {k: out.read_bytes() for k, (out, _ref) in PAIRS.items() if out.exists()}
    with contextlib.ExitStack() as stack:
        stack.enter_context(pd.cache_on())
        try:
            staged = staged_boundaries(tables.layout_editor(tables.loads(built["staging"]).root, PANEL))
        except (CandidateError, blb.BuildError) as exc:
            print(f"ERROR: {exc}")
            return 1
        if args.check:
            if not STAGED_BOUNDARIES.exists() or STAGED_BOUNDARIES.read_text(encoding="utf-8") != staged:
                print(f"STALE: {paths.rel(STAGED_BOUNDARIES)}; run {paths.rel(Path(__file__))}")
                return 1
            print(f"ok: {paths.rel(STAGED_BOUNDARIES)} current")
            return 0
        _, le_mod, _ = blb.plugin()
        if not STAGED_BOUNDARIES.exists() or STAGED_BOUNDARIES.read_text(encoding="utf-8") != staged:
            STAGED_BOUNDARIES.parent.mkdir(parents=True, exist_ok=True)
            STAGED_BOUNDARIES.write_text(staged, encoding="utf-8")
            print(f"wrote {paths.rel(STAGED_BOUNDARIES)}")
        import le_inputs
        overlay = le_inputs.load().overlay
        roots = {k: (tables.loads(built[k]).root, tables.read(ref)) for k, (_o, ref) in PAIRS.items()}
        try:
            lamps_root = with_parked_lamps(built["staging"], le_mod)
        except CandidateError as exc:
            print(f"ERROR: {exc}")
            return 1
        lines = [f"### Staging alone: {paths.rel(PAIRS['staging'][0])} (trial) against "
                 f"{paths.rel(PAIRS['staging'][1])} (current)", ""]
        lines += diff(*roots["staging"], le_mod, overlay, lamps_root)
        lines += ["", "", f"### Three levels: {paths.rel(PAIRS['all'][0])} (trial) against "
                          f"{paths.rel(PAIRS['all'][1])} (current)", ""]
        lines += diff(*roots["all"], le_mod, None)
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {paths.rel(REPORT)}")
        if not args.no_images:
            trial_root, ref_root = roots["staging"]
            for which, root in (("trial", trial_root), ("current", ref_root), ("lamps", lamps_root),
                                ("all", roots["all"][0])):
                panel = tables.layout_editor(root, PANEL)
                title = {"trial": f"{PANEL}: device-map staging candidate (panel_items.json, no overlay)",
                         "current": f"{PANEL}: current staging candidate (frozen inputs and overlay)",
                         "lamps": f"{PANEL}: the device-map candidate with the parked lamps and stations put back",
                         "all": f"{PANEL}: device-map candidate, three levels"}
                render_panel(panel, le_mod, IMAGES[which], title[which])
                print(f"wrote {IMAGES[which]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
