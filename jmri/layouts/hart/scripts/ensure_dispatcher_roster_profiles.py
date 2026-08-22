#!/usr/bin/env python3
"""Give every live DecoderPro roster entry a Dispatcher-usable speed profile.

Dispatcher System registration (`get_all_roster_entries_with_speed_profile`)
only lists locos whose roster file contains <speedprofile>. 2091 already has
the HART synthetic 10-step / 400 mm/s profile. This copies that profile into
any other locomotive named by roster.xml.

Existing profiles are left alone (measured data wins). Does not write decoder
CVs. Re-run after pulling a fresh roster from the Pi.

  python3 jmri/layouts/hart/scripts/ensure_dispatcher_roster_profiles.py \\
      --roster-dir jmri/host-copies/pi-roster-ops
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ROSTER = ROOT / "jmri/host-copies/pi-roster-ops"

# Same linear HO profile stored on 2091 (mm/s vs 0–1000 JMRI speed steps).
PROFILE_STEPS = [
    (100, 40.0),
    (200, 80.0),
    (300, 120.0),
    (400, 160.0),
    (500, 200.0),
    (600, 240.0),
    (700, 280.0),
    (800, 320.0),
    (900, 360.0),
    (1000, 400.0),
]


def synthetic_profile_xml() -> str:
    speeds = "\n".join(
        "        <speed>\n"
        f"          <step>{step}</step>\n"
        f"          <forward>{mm_s}</forward>\n"
        f"          <reverse>{mm_s}</reverse>\n"
        "        </speed>"
        for step, mm_s in PROFILE_STEPS
    )
    return (
        "    <speedprofile>\n"
        "      <overRunTimeForward>0.0</overRunTimeForward>\n"
        "      <overRunTimeReverse>0.0</overRunTimeReverse>\n"
        "      <speeds>\n"
        f"{speeds}\n"
        "      </speeds>\n"
        "    </speedprofile>\n"
    )


def resolve_roster_paths(base: Path) -> tuple[Path, Path]:
    base = base.expanduser().resolve()
    if (base / "roster.xml").is_file() and (base / "roster").is_dir():
        return base / "roster.xml", base / "roster"
    if (base / "roster.xml").is_file():
        return base / "roster.xml", base
    raise FileNotFoundError(f"no roster.xml under {base}")


def live_loco_files(roster_xml: Path, roster_dir: Path) -> list[tuple[str, Path]]:
    tree = ET.parse(roster_xml)
    out: list[tuple[str, Path]] = []
    for loco in tree.getroot().findall("roster/locomotive"):
        ident = (loco.get("id") or "").strip()
        name = (loco.get("fileName") or "").strip()
        if not name:
            continue
        path = roster_dir / name
        out.append((ident or name, path))
    return out


def ensure_profile(path: Path) -> str:
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8")
    if re.search(r"<speedprofile\b", text):
        return "has-profile"
    profile = synthetic_profile_xml()
    if "<values>" in text:
        text = text.replace("<values>", profile + "    <values>", 1)
    elif "</locomotive>" in text:
        text = text.replace("</locomotive>", profile + "  </locomotive>", 1)
    else:
        return "no-insert-point"
    path.write_text(text, encoding="utf-8")
    return "added"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--roster-dir",
        type=Path,
        default=DEFAULT_ROSTER,
        help="Directory that contains roster.xml and roster/*.xml",
    )
    args = ap.parse_args()
    try:
        roster_xml, loco_dir = resolve_roster_paths(args.roster_dir)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    added: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    for ident, path in live_loco_files(roster_xml, loco_dir):
        status = ensure_profile(path)
        if status == "added":
            added.append(ident)
        elif status == "has-profile":
            skipped.append(ident)
        else:
            missing.append(f"{ident} ({path.name}: {status})")

    print(f"roster.xml: {roster_xml}")
    print(f"loco files: {loco_dir}")
    print(f"added synthetic profile: {len(added)} {added}")
    print(f"already had a profile: {len(skipped)} {skipped}")
    if missing:
        print(f"skipped: {missing}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
