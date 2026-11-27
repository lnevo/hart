"""The PanelPro round trip (ADR-029 gate 2): a Store of the generated tables.xml and the generated file must be the
same bytes once both are normalised (tables_normal.normalise_store), and every staging block must get a derived
block path. tools/hosts/run_panelpro_roundtrip.sh runs it:

    python3 -m hartlib.tables_roundtrip roundtrip --store S --paths P [--generated G]
"""
from __future__ import annotations

import argparse
import difflib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from . import devices, paths, railroad, tables
from .tables_normal import normalise_store
from .tables_sections import TablesBuildError, finish


def roundtrip_differences(store: bytes, generated: bytes, context: int = 40) -> list[str]:
    """[] when a PanelPro Store of the generated tables and the generated tables are the same bytes once both are
    normalised (normalise_store); else the first `context` lines of a unified diff (generated against Store).
    ADR-029 gate 2."""
    sides = []
    for data in (generated, store):
        doc = tables.loads(data)
        normalise_store(doc.root)
        sides.append(doc.tobytes())
    want, got = sides
    if got == want:
        return []
    diff = difflib.unified_diff(want.decode("utf-8").splitlines(), got.decode("utf-8").splitlines(),
                                "generated", "store (normalised)", lineterm="", n=1)
    return [line for _i, line in zip(range(context), diff)]


def without_panels(data: bytes) -> bytes:
    """Tables bytes with every Layout Editor panel taken out: the round trip reports the beans and the panel apart."""
    doc = tables.loads(data)
    for le in tables.layout_editors(doc.root):
        tables.remove_child(doc.root, le)
    finish(doc.root)
    return doc.tobytes()


def read_path_counts(path: Path) -> dict[str, tuple[str, int]]:
    """{block system name: (user name, path count)} of the round trip's block path file."""
    out = {}
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3 or not parts[2].isdigit():
                raise TablesBuildError(f"{path}: line {n} is not system name, user name, path count")
            out[parts[0]] = (parts[1], int(parts[2]))
    return out


def roundtrip_report(store: Path, counts: Path, generated: Path) -> tuple[bool, list[str]]:
    """(passed, lines) of a PanelPro round trip: the normalised Store against the generated file, and the block
    paths JMRI derived for the blocks of the device master (every staging block must have at least one)."""
    lines, ok = [], True
    try:
        diff = roundtrip_differences(store.read_bytes(), generated.read_bytes())
        paths_of = read_path_counts(counts)
    except OSError as exc:
        return False, [f"cannot read {exc.filename}: {exc.strerror}"]
    staging = [r.jmri_name for r in devices.load()
               if r.level_cell == railroad.STAGING_LEVEL and r.layer == "block" and r.assignment != "none"
               and not r.part_of]
    none = [b for b in staging if paths_of.get(b, ("", 0))[1] == 0]
    total = sum(n for _u, n in paths_of.values())
    lines.append(f"block paths JMRI derived: {total} on {len(paths_of)} blocks "
                 f"({sum(paths_of.get(b, ('', 0))[1] for b in staging)} on the {len(staging)} staging blocks)")
    if none:
        ok = False
        lines.append(f"FAIL: staging blocks with no derived path: {', '.join(none)}")
    if diff:
        ok = False
        lines.append("FAIL: the normalised Store differs from the generated tables.xml:")
        rest = roundtrip_differences(without_panels(store.read_bytes()), without_panels(generated.read_bytes()))
        lines.append("  without the Layout Editor panels: " + ("identical" if not rest else "they differ too"))
        lines += [f"  {line}" for line in diff]
    else:
        lines.append("ok: the Store and the generated tables.xml are the same bytes once both are normalised "
                     "(normalise_store)")
    lines.append("PASS: the PanelPro round trip gives the generated tables.xml back" if ok
                 else "FAIL: the PanelPro round trip does not give the generated tables.xml back")
    return ok, lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hartlib.tables_roundtrip",
                                 description="Compare a PanelPro round trip's Store with the generated tables.xml.")
    ap.add_argument("action", choices=("roundtrip",))
    ap.add_argument("--store", type=Path, required=True, help="the Store PanelPro wrote")
    ap.add_argument("--paths", type=Path, required=True, help="the block path counts the round trip wrote")
    ap.add_argument("--generated", type=Path, default=paths.REPO_TABLES_XML)
    args = ap.parse_args(argv)
    try:
        ok, lines = roundtrip_report(args.store, args.paths, args.generated)
    except (TablesBuildError, devices.DevicesError, ET.ParseError) as exc:
        print(f"tables_roundtrip: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
