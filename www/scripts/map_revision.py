"""map_revision.py [--check]

Writes the system schematic's revision and date (the title block in the page's preferences file) into the station
map data and pages: www/data/crew.json, www/data/publications.json and each current www/crew/maps/<id>/index.html.
The work, and the list of what it writes and leaves alone, is hartlib.map_revision
(tools/hartlib/src/hartlib/map_revision.py), which tools/schematic/publish_draft.py shares: it applies it after it
publishes, and its --check runs the check. --check here exits 1 and names each place that differs, without writing;
www/scripts/tests/test_station_maps.py runs it in CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.map_revision import (PUB_LINE, REPO, SCHEMATIC, apply, drift, fields,  # noqa: E402,F401
                                  page_prefs, planned, pub_line)


def main(argv: list[str]) -> int:
    if argv not in ([], ["--check"]):
        print(__doc__.split("\n\n")[0])
        return 2
    rev, effective = fields()
    rel = lambda p: p.relative_to(REPO).as_posix()
    if argv:
        stale = drift()
        if stale:
            print(f"station maps differ from schematic revision {rev} ({effective}): "
                  + ", ".join(map(rel, stale)) + "; run python3 www/scripts/map_revision.py")
            return 1
        print(f"station maps carry schematic revision {rev} ({effective})")
        return 0
    changed = apply()
    print(f"station maps set to schematic revision {rev} ({effective}): " + ", ".join(map(rel, changed))
          if changed else f"station maps already carry schematic revision {rev} ({effective})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
