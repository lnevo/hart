#!/usr/bin/env python3
"""Build the public wiring viewer data (behind/wiring.html) from the wiring model.

Reads the LCOS inventory's sheets as tools/wiring/write_inventory.py builds them in memory from the wiring model
(the device master, hartlib.wiring's wiring.csv, lcos_nodes.csv and signal_head_plan.csv), the same sheets it saves
as LCOS_Layout_Inventory_v86.xlsx. The workbook file is an output only: this script never opens it (ADR-039). It
writes:

  data/wiring-inventory.json  nodes with DNOU8 / DNIN8 / block-detector port maps,
                              signal heads with their R/Y/G pins, turnouts, block sensors

The JSON is not committed (ADR-036): the site build and the local preview build it with view() (site_views.py,
make site-data), and --check builds it in memory and runs its checks (problems()). To write it by hand:

  python3 www/scripts/build_wiring_json.py           # www/data/wiring-inventory.json (--out-dir for another folder)
  python3 www/scripts/build_wiring_json.py --check   # build in memory, exit 1 when it cannot be built or fails a check

The sheets are read into viewer data by wiring_inventory.Inventory (its cell helpers are in wiring_sheet.py); this
script cleans the cells first, then checks and writes what Inventory built. Data problems found along the way are
printed as warnings; they do not stop the build. Network details (IP
addresses, hostnames, serial ports, machine paths, credentials) are scrubbed from every cell before it reaches the
JSON, and problems() fails a built JSON that still holds one.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

HERE = Path(__file__).resolve().parent
PORTAL = HERE.parent
ROOT = PORTAL.parent
OUT_INV = PORTAL / "data" / "wiring-inventory.json"
OUT_REL = OUT_INV.relative_to(PORTAL).as_posix()  # its path in the site (site_views.VIEWS)
sys.path[:0] = [str(HERE), str(ROOT / "tools" / "wiring")]
import write_inventory  # noqa: E402  (the wiring model's inventory sheets; it puts hartlib on the path)
# the sheets' reader; the names the tests and site_views.py take from this module are re-exported
from wiring_inventory import NEEDED_SHEETS, Built, BuildLog, Inventory, ViewerData  # noqa: E402
from wiring_inventory import WiringDataError as WiringDataError  # noqa: E402
from wiring_inventory import crossover_half as crossover_half, turnout_name as turnout_name  # noqa: E402
from wiring_sheet import OutKind as OutKind, out_kind as out_kind  # noqa: E402


# —— Cell cleanup ————————————————————————————————————————————————

# Anything that looks like a network detail, a machine path or a secret. A matching cell
# is dropped whole rather than half-redacted.
UNSAFE = [
    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),  # IPv4
    re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I),  # MAC
    re.compile(r"\b[\w-]+\.(?:local|lan|home|internal)\b", re.I),  # mDNS / LAN hosts
    re.compile(r"\b(?:mqtt|tcp|ws|wss|http|https)://", re.I),
    re.compile(r"\bCOM\d+\b"),
    re.compile(r"/dev/(?:tty|cu)\S*"),
    re.compile(r"(?:/Users/|/home/|[A-Z]:\\)"),
    re.compile(r"\b(?:password|passwd|pwd|secret|token|api[_ -]?key|ssid|wi-?fi|psk|credential)s?\b", re.I),
    re.compile(r"\bbroker\b", re.I),
]


def clean(v: object, scrubbed: list[str]) -> str:
    """A cell as one line of text; a cell that looks like a network detail or a secret is dropped whole and noted in
    scrubbed."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (dt.datetime, dt.date)):
        v = v.isoformat()[:10]
    s = re.sub(r"\s+", " ", str(v)).strip()
    for pat in UNSAFE:
        if pat.search(s):
            scrubbed.append(s)
            return ""
    return s


def sheet_rows(ws: Worksheet, scrubbed: list[str]) -> list[list[str]]:
    """Every row as cleaned strings, empty rows dropped."""
    out = []
    for row in ws.iter_rows(values_only=True):
        cells = [clean(c, scrubbed) for c in row]
        if any(cells):
            out.append(cells)
    return out


def read_sheets(wb: Workbook | None, source: str, log: BuildLog) -> dict[str, list[list[str]]]:
    """Every sheet's cleaned rows: by default the workbook write_inventory.py builds in memory from the wiring model."""
    try:
        wb = wb if wb is not None else write_inventory.workbook()
    except write_inventory.FactsError as err:
        raise WiringDataError(f"the wiring model cannot be read: {err}") from err
    sheets = {ws.title: sheet_rows(ws, log.scrubbed) for ws in wb.worksheets}
    missing = [need for need in NEEDED_SHEETS if need not in sheets]
    if missing:
        raise WiringDataError(f"{source}: missing sheet(s) {', '.join(missing)}")
    return sheets


def build_inventory(wb: Workbook | None = None, source: str = write_inventory.OUT.name) -> Built:
    """The viewer's data from the inventory sheets of wb, with the warnings and scrubbed cells of this build. source is
    the file write_inventory.py saves the workbook as, for the JSON's source."""
    log = BuildLog()
    inv = Inventory(read_sheets(wb, source, log), source, log)
    inv.read_nodes()
    inv.read_outputs()
    inv.read_inputs()
    inv.read_blocks()
    port_rows, mast_rows = inv.digicon_tables()
    inv.read_digicon_heads(port_rows)
    inv.read_led_heads()
    inv.read_masts(mast_rows)
    inv.check_node_signals()
    inv.read_turnouts()
    inv.check_declared_boards()
    return Built(inv.data(), log)


def prune(x: object) -> object:
    """Drop empty-string fields so the JSON only carries what a cell actually says."""
    if isinstance(x, dict):
        return {k: prune(v) for k, v in x.items() if v != ""}
    if isinstance(x, list):
        return [prune(v) for v in x]
    return x


# —— Main ——————————————————————————————————————————————————————————

def shown(path: Path) -> str:
    """path relative to the repo when it lies inside it, for messages."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def render(data: ViewerData) -> str:
    """The JSON text of built viewer data, its empty fields pruned."""
    return json.dumps(prune(data), indent=1, ensure_ascii=False) + "\n"


# Lists every wiring model fills; an empty one means the model or the reader is broken.
REQUIRED = ("nodes", "signals", "masts", "turnouts", "blocks")


def _strings(x: object) -> Iterator[str]:
    """Every key and string value in x, at any depth."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def problems(inv: Mapping[str, Any]) -> list[str]:
    """What is wrong with built viewer data: no source, a required list that is empty, a node id empty or twice, or a
    string that still looks like a network detail or a secret (clean() should have dropped it)."""
    out = []
    if not (inv.get("source") or {}).get("file"):
        out.append("source.file is empty")
    for key in REQUIRED:
        if not isinstance(inv.get(key), list) or not inv[key]:
            out.append(f"{key!r} has no entries")
    ids = [n.get("id") for n in inv.get("nodes") or []]
    twice = sorted({i for i in ids if ids.count(i) > 1})
    if twice or not all(ids):
        out.append(f"node ids are not one each: {twice or 'an empty id'}")
    leaks = sorted({s for s in _strings(inv) if any(p.search(s) for p in UNSAFE)})
    if leaks:
        out.append(f"{len(leaks)} string(s) look like network details or secrets: {leaks[:3]}")
    return out


def data_text(inv: ViewerData) -> str:
    """The checked wiring-inventory.json text of built viewer data. WiringDataError when it fails a check."""
    bad = problems(inv)
    if bad:
        raise WiringDataError("www/%s fails its checks:\n  %s" % (OUT_REL, "\n  ".join(bad)))
    return render(inv)


def build(wb: Workbook | None = None) -> Built:
    """The viewer data from the wiring model, dated today (its build date)."""
    built = build_inventory(wb)
    built.data["source"]["built"] = dt.date.today().isoformat()
    return built


def view() -> str:
    """The viewer data for the site build and the local preview (site_views.VIEWS)."""
    return data_text(build().data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", type=Path, default=PORTAL / "data", help="where the JSON goes")
    ap.add_argument("-q", "--quiet", action="store_true", help="don't list data warnings")
    ap.add_argument("--check", action="store_true",
                    help="write nothing; build the JSON in memory and exit 1 when it cannot be built or fails a check")
    args = ap.parse_args()
    try:
        inv, log = build()
    except WiringDataError as exc:  # the model cannot be read: 2
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 2
    try:
        text = data_text(inv)
    except WiringDataError as exc:  # built, but fails a check
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 1
    if args.check:
        print(f"www/{OUT_REL} builds from the wiring model and passes its checks (not committed, ADR-036)")
    else:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        p = args.out_dir / OUT_INV.name
        p.write_text(text, encoding="utf-8")
        print(f"wrote {shown(p)} ({p.stat().st_size // 1024} KB)")

    n_pins = sum(len(b["pins"]) for n in inv["nodes"] for b in n["outputs"] + n["inputs"])
    print(f"{inv['source']['file']}: {len(inv['nodes'])} nodes, {n_pins} pins, {len(inv['signals'])} heads, "
          f"{len(inv['turnouts'])} turnouts, {len(inv['blocks'])} block sensors")
    if log.scrubbed:
        print(f"scrubbed {len(log.scrubbed)} cell(s) that looked like network details or secrets")
    if log.warnings:
        print(f"{len(log.warnings)} data warning(s)" + ("" if args.quiet else ":"))
        if not args.quiet:
            for w in log.warnings:
                print("  - " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
