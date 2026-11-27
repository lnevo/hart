#!/usr/bin/env python3
"""Write mimic_layout.json for the JMRI-hosted mimic page (jmri/resources/jmri-web/mimic/).

Same layout the Mac mimic serves at /api/layout, built from tables.xml and the repo
CSVs. The deploy runs this into the staged web folder, so the hosts get a fresh copy.

  python3 tools/mqtt-mimic/build_mimic_web.py --out <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# lcos_mqtt_mimic puts tools/hartlib/src on sys.path, so hartlib imports after it
from lcos_mqtt_mimic import MimicError, load_layout  # noqa: E402
from mimic_records import Layout  # noqa: E402

from hartlib import devices  # noqa: E402

FILENAME = "mimic_layout.json"


def write(out_dir: Path, layout: Layout) -> Path:
    """Write layout to out_dir/FILENAME and return that path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FILENAME
    path.write_text(json.dumps(layout, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path, help="folder that holds index.html")
    out = ap.parse_args().out
    try:
        layout = load_layout()
    except MimicError as exc:      # tables.xml is missing, or a device-map row the page cannot place
        raise SystemExit(str(exc)) from exc
    except devices.DevicesError as exc:      # a bad row in the device master, naming file, line and row
        raise SystemExit(f"build_mimic_web.py: the device master cannot be used: {exc}") from exc
    try:
        path = write(out, layout)
    except OSError as exc:      # the folder cannot be made or the file cannot be written
        raise SystemExit(f"build_mimic_web.py: cannot write {out / FILENAME}: {exc}") from exc
    print(f"{path}: {len(layout['turnouts'])} turnouts, {len(layout['blocks'])} blocks, {len(layout['heads'])} heads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
