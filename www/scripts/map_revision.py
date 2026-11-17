"""map_revision.py [--check]

The station maps are drawn from the system schematic, so the site gives them the schematic's revision and date.
The title block's `revision` and `date` in jmri/layouts/hart/data/schematic/main_upper.preferences.json are the
only source. This writes them into:

- www/data/crew.json: `schematic.revision` and `schematic.effective` (crew.js shows them on the maps index and on
  every current station map page);
- www/data/publications.json: the `revision` of SM-01 and of each current station map entry;
- www/crew/maps/<id>/index.html: the publication line each current map page shows before its script runs.

The archive pages (www/crew/maps/archive/) and the archive fields of each map in crew.json (`revision`,
`effective`) describe the earlier hand-drawn sheets and are left alone.

tools/schematic/publish_draft.py runs this after it publishes, and its --check runs the check. --check here exits 1
and names each place that differs, without writing; www/scripts/tests/test_station_maps.py runs it in CI.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PREFS = REPO / "jmri/layouts/hart/data/schematic/main_upper.preferences.json"
PUB_LINE = re.compile(r'(<p class="sheet-pub" id="page-pub">)([^<]*)(</p>)')


def fields(prefs: Path = PREFS) -> tuple[str, str]:
    """(revision, effective) from the title block: ("10", "16 November 2026")."""
    p = json.loads(prefs.read_text())
    rev, date = p.get("revision"), p.get("date")
    if rev is None or isinstance(rev, bool) or not str(rev).strip():
        raise ValueError(f"{prefs.name}: no revision in the title block")
    try:
        day = datetime.date.fromisoformat(str(date))
    except ValueError:
        raise ValueError(f"{prefs.name}: date {date!r} is not YYYY-MM-DD") from None
    return str(rev).strip(), f"{day.day} {day:%B %Y}"


def pub_line(pub: str, rev: str, effective: str) -> str:
    return f"Publication {pub} · Revision {rev} · Effective {effective}"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def planned(www: Path, prefs: Path = PREFS) -> dict[Path, str]:
    """{file: text it should have} for every file this owns, from the files as they are now."""
    rev, effective = fields(prefs)
    crew_path, pubs_path = www / "data/crew.json", www / "data/publications.json"
    crew, pubs = _load(crew_path), _load(pubs_path)
    sc = crew["schematic"]
    sc["revision"], sc["effective"] = rev, effective

    pages = {f"crew/maps/{m['id']}/index.html": m for m in crew["maps"]}
    found = set()
    for item in pubs["items"]:
        if item.get("page") == sc["svg"] or item.get("page") in pages:
            item["revision"] = rev
            found.add(item["page"])
    missing = sorted(({sc["svg"]} | set(pages)) - found)
    if missing:
        raise ValueError(f"publications.json lists no entry for {', '.join(missing)}")

    out = {crew_path: _dump(crew), pubs_path: _dump(pubs)}
    for rel, m in pages.items():
        page = www / rel
        text = page.read_text(encoding="utf-8")
        if len(PUB_LINE.findall(text)) != 1:
            raise ValueError(f"{rel}: expected one page-pub line")
        out[page] = PUB_LINE.sub(lambda g: g[1] + pub_line(m["pub"], rev, effective) + g[3], text)
    return out


def drift(www: Path = REPO / "www", prefs: Path = PREFS) -> list[Path]:
    """Files whose revision or date differs from the title block ([] when they all match)."""
    return [p for p, text in planned(www, prefs).items() if p.read_text(encoding="utf-8") != text]


def apply(www: Path = REPO / "www", prefs: Path = PREFS) -> list[Path]:
    """Write the title block's revision and date into every file that differs; returns those files."""
    plan = planned(www, prefs)
    changed = [p for p, text in plan.items() if p.read_text(encoding="utf-8") != text]
    for p in changed:
        p.write_text(plan[p], encoding="utf-8")
    return changed


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
