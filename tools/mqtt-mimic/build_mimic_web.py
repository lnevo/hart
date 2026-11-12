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
from lcos_mqtt_mimic import load_layout  # noqa: E402

FILENAME = "mimic_layout.json"


def write(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FILENAME
    path.write_text(json.dumps(load_layout(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path, help="folder that holds index.html")
    path = write(ap.parse_args().out)
    layout = json.loads(path.read_text(encoding="utf-8"))
    print(f"{path}: {len(layout['turnouts'])} turnouts, {len(layout['blocks'])} blocks, {len(layout['heads'])} heads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
