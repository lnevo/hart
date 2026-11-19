#!/usr/bin/env python3
"""Put a generated Layout Editor panel's lamps and block contents labels back after Dispatcher System Stage 1.

The Dispatcher System is parked (hartlib.parked), so this runs only once it is unparked: run_panelpro_stage1.sh runs
it after Stage 1, with ``--reference`` the tables as they were before Stage 1. Stage 1 (CreateIcons) deletes and
re-adds the occupancy lamps and the block contents labels at its own spots, and its Store writes the labels at level 0,
behind the panel background. This puts them back, taking every position from the panels themselves:

- each block contents label on the label layer (level 4), in black, with the plugin's Dialog font or none, and where
  the same block's label stands on the ``--reference`` panel;
- each Stage 1 lamp, one per sensor, where that sensor's lamp stands on the ``--reference`` panel; without a
  reference where the panel's own one lamp stands; else at the computed spot (the turnout circle's centre, or the
  middle of the track), printed as a note. A missing switch OS lamp (OS_OCCUPANCY_ICONS) is added;
- with ``--reference``, a Stage 1 lamp on a sensor the reference panel shows no lamp for is removed: Stage 1 adds one
  on every block sensor, the main and upper levels' too, and the panel shows only the ones the build gave it;
- every lamp display only (a click must never set occupancy).

Nothing else on the panel changes at Stage 1 (stock CreateIcons.removeIconsAndLabels and addIcons): it leaves the
mast icons, the captions and the panel's attributes alone, so they keep what the build gave them.

The level-12 lamps of the Dispatcher station clusters belong to reconcile_dispatcher_stations.py and are left alone.
The main panel must be a generated one (hartlib.tables.require_generated_panel), and so must the reference's. Tables
whose Dispatcher System is parked hold no Stage 1 to repair after: the run prints SKIPPED and changes nothing.
The writable source is ``jmri/layouts/hart/output/tables.xml``.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import parked, paths, tables  # noqa: E402

ROOT = paths.REPO_ROOT
DEFAULT_PANEL = paths.TABLES_XML

# Switch OS lamps that must exist (Dispatcher System Stage 1 occupancy dots). Where they go comes from lamp_targets().
OS_OCCUPANCY_ICONS = (
    "BS Switch 3",
    "BS Switch 1",
    "BS Switch 5",
    "BS Switch 13",
    "BS Switch 15",
    "BS Switch 17",
    "BS Switch 19",
    "BS Switch 21",
    "BS Switch 25",
    "BS Switch 27",
    "BS Switch 23a",
    "BS Switch 29",
    "BS Switch 31",
    "BS Switch 33",
    "BS Switch 11",
    "BS Switch 7",
    "BS Switch 9",
    "BS Switch 35b",
    "BS Switch 35a",
)
# The Dispatcher station clusters' lamps (reconcile_dispatcher_stations.py) stand on this level; Stage 1's on 10.
CLUSTER_LAMP_LEVEL = "12"

LAMP_SIZE = 10  # circuit-*.gif is 10x10; x/y is its top-left corner


def _set_xy(el: ET.Element, x: int, y: int) -> None:
    el.set("x", str(x))
    el.set("y", str(y))


def _xy(el: ET.Element, what: str) -> tuple[int, int]:
    try:
        return round(float(el.get("x"))), round(float(el.get("y")))
    except (TypeError, ValueError):
        raise ValueError(f"{what}: x={el.get('x')!r} y={el.get('y')!r} is not a position") from None


def _circuit_occupancy_icon(sensor: str, x: int, y: int) -> ET.Element:
    icon = ET.Element(
        "sensoricon",
        {
            "sensor": sensor,
            "x": str(x),
            "y": str(y),
            "level": "10",
            "forcecontroloff": "true",      # display only: a click must never set occupancy (owner, 2026-11-15)
            "hidden": "no",
            "positionable": "true",
            "showtooltip": "true",
            "editable": "true",
            "momentary": "false",
            "icon": "yes",
            "class": "jmri.jmrit.display.configurexml.SensorIconXml",
        },
    )
    for state, url in (
        ("active", "program:resources/icons/smallschematics/tracksegments/circuit-occupied.gif"),
        ("inactive", "program:resources/icons/smallschematics/tracksegments/circuit-empty.gif"),
        ("unknown", "program:resources/icons/smallschematics/tracksegments/circuit-error.gif"),
        ("inconsistent", "program:resources/icons/smallschematics/tracksegments/circuit-error.gif"),
    ):
        child = ET.SubElement(icon, state, {"url": url, "degrees": "0", "scale": "1.0"})
        ET.SubElement(child, "rotation").text = "0"
    ET.SubElement(icon, "iconmaps")
    return icon


def ensure_os_occupancy_icons(
    le: ET.Element, *, check: bool, targets: dict[str, tuple[int, int]]
) -> tuple[int, list[str]]:
    """Every switch OS lamp (OS_OCCUPANCY_ICONS) on the panel; a missing one is added at its target, before the
    first turnout (JMRI draws by level, not by order)."""
    changes = 0
    errors: list[str] = []
    existing = {(icon.get("sensor") or "").strip() for icon in le.findall("sensoricon")}
    missing = [name for name in OS_OCCUPANCY_ICONS if name not in existing]
    if check:
        return 0, [f"missing OS occupancy icon {name!r}" for name in missing]
    first_turnout = next((i for i, child in enumerate(le) if child.tag == "layoutturnout"), len(le))
    for name in missing:
        if name not in targets:
            errors.append(f"no target for missing OS occupancy icon {name!r}")
            continue
        le.insert(first_turnout, _circuit_occupancy_icon(name, *targets[name]))
        first_turnout += 1
        changes += 1
    return changes, errors


def _segment_ends(le: ET.Element) -> list[tuple[str, tuple[float, float], tuple[float, float], bool, str]]:
    """(block, end1, end2, curved, ident) for each shown track segment."""
    points = {
        pt.get("ident"): (float(pt.get("x")), float(pt.get("y")))
        for pt in le.findall("positionablepoint")
    }
    turnouts = {to.get("ident"): to for to in le.findall("layoutturnout")}

    def end(name: str | None, kind: str | None) -> tuple[float, float] | None:
        if name in points:
            return points[name]
        to = turnouts.get(name or "")
        if to is None:
            return None
        leg = {"TURNOUT_A": "a", "TURNOUT_B": "b", "TURNOUT_C": "c", "TURNOUT_D": "d"}.get(kind or "")
        if leg and to.get(f"x{leg}") is not None:
            return float(to.get(f"x{leg}")), float(to.get(f"y{leg}"))
        return float(to.get("xcen")), float(to.get("ycen"))

    out = []
    for ts in le.findall("tracksegment"):
        a = end(ts.get("connect1name"), ts.get("type1"))
        b = end(ts.get("connect2name"), ts.get("type2"))
        if a is None or b is None or ts.get("hidden") == "yes":
            continue
        curved = "yes" in (ts.get("arc"), ts.get("bezier"), ts.get("circle"))
        out.append((ts.get("blockname") or "", a, b, curved, ts.get("ident") or ""))
    return out


def computed_lamp_targets(root: ET.Element, le: ET.Element) -> dict[str, tuple[int, int]]:
    """Where each Stage 1 occupancy lamp goes when no panel has one for it, from the panel geometry.

    A sensor whose block is a switch's OS block goes in the centre of that turnout circle. Otherwise it goes in the
    middle of the longest straight segment of its track, leaving out hidden throat blocks that share it.
    """
    blocks_by_sensor: dict[str, list[str]] = {}
    throats: set[str] = set()
    for blocks in root.findall("blocks"):
        for block in blocks.findall("block"):
            sensor = (block.findtext("occupancysensor") or "").strip()
            name = (block.findtext("userName") or "").strip()
            if not sensor or not name:
                continue
            blocks_by_sensor.setdefault(sensor, []).append(name)
    # A hidden throat shares its station's detector and is named after it
    # ("Track S-1 West", "Track East Lead East"); no reliance on comments,
    # which Stage 1 drops.
    for names in blocks_by_sensor.values():
        for name in names:
            if any(name != other and name.startswith(other + " ") for other in names):
                throats.add(name)
    turnout_by_block: dict[str, ET.Element] = {}
    # Only a turnout's own block makes an OS block; per-leg blocks are track.
    for to in le.findall("layoutturnout"):
        if to.get("blockname"):
            turnout_by_block.setdefault(to.get("blockname"), to)
    segments = _segment_ends(le)
    half = LAMP_SIZE / 2
    targets: dict[str, tuple[int, int]] = {}
    for sensor, names in blocks_by_sensor.items():
        os_blocks = [n for n in names if n in turnout_by_block]
        if os_blocks:
            to = turnout_by_block[os_blocks[0]]
            cx, cy = float(to.get("xcen")), float(to.get("ycen"))
        else:
            # Straight track of the block itself first; a track drawn only as
            # curves falls back to its straight throat stub, since a curve's
            # chord midpoint can sit off the drawn track.
            mains = [n for n in names if n not in throats] or names
            main_pieces = [seg for seg in segments if seg[0] in mains]
            all_pieces = [seg for seg in segments if seg[0] in names]
            if not all_pieces:
                continue
            straight = (
                [seg for seg in main_pieces if not seg[3]]
                or [seg for seg in all_pieces if not seg[3]]
                or main_pieces
                or all_pieces
            )
            _b, a, b, _c, _i = max(
                straight, key=lambda seg: ((seg[1][0] - seg[2][0]) ** 2 + (seg[1][1] - seg[2][1]) ** 2, seg[4])
            )
            cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        targets[sensor] = (round(cx - half), round(cy - half))
    return targets


def _is_circuit_lamp(icon: ET.Element) -> bool:
    active = icon.find("active")
    # A bare test icon has no state children; treat it as a lamp.
    return active is None or "circuit-" in (active.get("url") or "")


def _stage1_lamps(le: ET.Element) -> dict[str, list[ET.Element]]:
    """{sensor: its Stage 1 circuit lamps} on a panel, leaving out the level-12 station cluster lamps."""
    out: dict[str, list[ET.Element]] = {}
    for icon in le.findall("sensoricon"):
        name = (icon.get("sensor") or "").strip()
        if name and icon.get("level") != CLUSTER_LAMP_LEVEL and _is_circuit_lamp(icon):
            out.setdefault(name, []).append(icon)
    return out


def reference_panel(path: Path | None) -> ET.Element | None:
    """The generated main panel of the --reference tables (the copy taken before Stage 1), or None."""
    if path is None:
        return None
    try:
        root = tables.read(path)
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"--reference {path}: {exc}") from None
    return tables.require_generated_panel(root, f"--reference {path}")


def lamp_targets(
    root: ET.Element, le: ET.Element, reference: ET.Element | None
) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """(targets, notes) for the panel's Stage 1 lamps; see the module docstring for the order."""
    computed = computed_lamp_targets(root, le)
    ref_lamps = _stage1_lamps(reference) if reference is not None else {}
    own = _stage1_lamps(le)
    targets: dict[str, tuple[int, int]] = {}
    notes: list[str] = []
    for sensor in sorted(set(computed) | set(OS_OCCUPANCY_ICONS)):
        ref = ref_lamps.get(sensor, [])
        mine = own.get(sensor, [])
        if len(ref) == 1:
            targets[sensor] = _xy(ref[0], f"reference lamp {sensor}")
        elif len(mine) == 1 and reference is None:
            targets[sensor] = _xy(mine[0], f"lamp {sensor}")
        elif sensor in computed:
            targets[sensor] = computed[sensor]
            if mine or ref:
                why = (f"{len(ref)} on the reference panel" if reference is not None
                       else f"{len(mine)} on the panel")
                notes.append(f"lamp {sensor}: {why}, so it goes to the computed spot {computed[sensor]}")
    return targets, notes


def bci_spots(reference: ET.Element | None) -> dict[str, tuple[int, int]]:
    """{block: (x, y)} of each block contents label that stands once on the reference panel."""
    if reference is None:
        return {}
    by_block: dict[str, list[ET.Element]] = {}
    for icon in reference.findall("BlockContentsIcon"):
        by_block.setdefault(icon.get("blockcontents") or "", []).append(icon)
    return {b: _xy(icons[0], f"reference block contents {b}") for b, icons in by_block.items()
            if b and len(icons) == 1}


def _is_display_lamp(icon: ET.Element) -> bool:
    """A lamp that shows state and must not take a click: an occupancy lamp (block sensor "BS ...") or any icon
    drawn with the circuit-* lamp images (Stage 1's occupancy and move-in-progress lamps)."""
    active = icon.find("active")
    return ((icon.get("sensor") or "").startswith("BS ")
            or (active is not None and "circuit-" in (active.get("url") or "")))


def lamps_display_only(le: ET.Element, *, check: bool, name: str = "") -> tuple[int, list[str]]:
    """Every lamp on the panel display only (forcecontroloff="true"). A switch OS lamp sits in its turnout
    circle, so a clickable lamp took the turnout click and set the block occupied on every host (owner,
    2026-11-15). Stage 1's Store writes its lamps clickable; this puts them back."""
    changes, errors = 0, []
    for icon in le.findall("sensoricon"):
        if _is_display_lamp(icon) and icon.get("forcecontroloff") != "true":
            if check:
                errors.append(f"{name}: lamp {icon.get('sensor')!r} can be clicked")
            else:
                icon.set("forcecontroloff", "true")
                changes += 1
    return changes, errors


def place_stage1_lamps(
    le: ET.Element, *, check: bool, targets: dict[str, tuple[int, int]]
) -> tuple[int, list[str]]:
    """Put each Stage 1 occupancy lamp on its target, one lamp per sensor.

    A copy already on the target is the one kept; any other Stage 1 copy of
    the same sensor is removed, so copies never stack on one spot.
    """
    changes = 0
    errors: list[str] = []
    for name, icons in _stage1_lamps(le).items():
        if name not in targets:
            continue
        x, y = targets[name]
        on_spot = [i for i in icons if tables.same_number(i.get("x"), x) and tables.same_number(i.get("y"), y)]
        keep = on_spot[0] if on_spot else icons[0]
        for extra in icons:
            if extra is keep:
                continue
            if check:
                errors.append(f"{name}: more than one Stage 1 lamp")
            else:
                le.remove(extra)
                changes += 1
        if keep in on_spot:
            continue
        if check:
            errors.append(f"{name} at ({keep.get('x')}, {keep.get('y')}), expected ({x}, {y})")
        else:
            _set_xy(keep, x, y)
            changes += 1
    return changes, errors


def drop_lamps_not_on(le: ET.Element, reference: ET.Element, *, check: bool) -> tuple[int, list[str]]:
    """Remove each Stage 1 lamp whose sensor has no Stage 1 lamp on the `reference` panel (Stage 1 adds one on every
    block sensor); a switch OS lamp (OS_OCCUPANCY_ICONS) always stays."""
    keep = set(_stage1_lamps(reference)) | set(OS_OCCUPANCY_ICONS)
    changes, errors = 0, []
    for name, icons in _stage1_lamps(le).items():
        if name in keep:
            continue
        if check:
            errors.append(f"{name}: {len(icons)} Stage 1 lamp(s), none on the reference panel")
            continue
        for icon in icons:
            le.remove(icon)
            changes += 1
    return changes, errors


def dispatcher_parked(root: ET.Element) -> bool:
    """True when these tables leave the Dispatcher System out (hartlib.parked): no Stage 1 to repair after."""
    return "dispatcher" in parked.parked_in(root)


def repair(path: Path, *, check: bool = False, reference: Path | None = None) -> tuple[int, list[str]]:
    """(changes, errors) of putting the panel in `path` back after Stage 1 (module docstring); --check writes
    nothing. ValueError when the panel or the reference's is not generated, or the tables hold no Dispatcher
    System (parked: no Stage 1 to repair after)."""
    doc = tables.load(path)
    root = doc.root
    le = tables.require_generated_panel(root, path.name)
    if dispatcher_parked(root):
        raise ValueError(f"{path.name}: the Dispatcher System is parked in these tables (hartlib.parked), so there "
                         "is no Stage 1 to repair after")
    ref = reference_panel(reference)
    changes, errors = tables.ensure_block_contents_visible(le, check=check, spots=bci_spots(ref))
    errors = [f"{path.name}: {e}" for e in errors]
    if ref is not None:
        n, errs = drop_lamps_not_on(le, ref, check=check)
        changes += n
        errors.extend(f"{path.name}: {e}" for e in errs)
    targets, notes = lamp_targets(root, le, ref)
    for note in notes:
        print(f"note: {path.name}: {note}")
    for step in (ensure_os_occupancy_icons, place_stage1_lamps):
        n, errs = step(le, check=check, targets=targets)
        changes += n
        errors.extend(f"{path.name}: {e}" for e in errs)
    n, errs = lamps_display_only(le, check=check, name=path.name)
    changes += n
    errors.extend(errs)
    if not check and changes:
        doc.save(path)
    return changes, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument("--check", action="store_true", help="report what a run would change; write nothing")
    ap.add_argument("--reference", type=Path,
                    help="the tables before Stage 1 (run_panelpro_stage1.sh): lamps and block contents labels go "
                         "back where they stood in it")
    args = ap.parse_args()
    if not args.check:
        paths.exit_if_overridden(Path(__file__).name)
    path = args.panel.resolve()
    if not path.is_file():
        print(f"FAIL\n  - missing {path}")
        return 1
    try:
        if dispatcher_parked(tables.read(path)):
            # as reconcile_dispatcher_stations.py: parked, there is no Stage 1 to repair after
            print(f"SKIPPED: the Dispatcher System is parked (hartlib.parked.PARKED); {path.name} holds no Stage 1 "
                  "lamps to repair")
            return 0
    except (OSError, ET.ParseError) as exc:
        print(f"FAIL\n  - {path}: {exc}")
        return 1
    try:
        changes, errors = repair(path, check=args.check, reference=args.reference)
    except RuntimeError as exc:  # hartlib save refuses, e.g. during a HART_TABLES check run
        errors = [f"{path}: not changed: {exc}"]
    except ValueError as exc:  # no generated panel, a bad --reference, a doubled marker, the Dispatcher parked
        errors = [f"{path}: {exc}"]
    else:
        verb = "checked" if args.check else "updated"
        print(f"{verb} {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: {changes} changes")
    if errors:
        print("FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS" if args.check else "Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
