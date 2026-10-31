#!/usr/bin/env python3
"""Keep the shared ~/Desktop/HART folders and their repo copies in step, both ways.

Previews by default; pass --apply to copy. A file that is new or changed on one
side is copied to the other, and nothing is ever deleted. A file that changed on
both sides is reported and left alone: make the two copies match, then run again.
Hashes from the last run are kept in .sync_state.json beside the mirrors, so on a
first run every differing file is reported as a conflict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIRROR = ROOT / "external/desktop-data"
DESKTOP = Path.home() / "Desktop/HART"
STATE = MIRROR / ".sync_state.json"
PAIRS = {
    "Car Cards/CarImagesFinal": "car-images/CarImagesFinal",
    "Car Cards/docs": "car-cards/docs",
    "Wiring Documentation": "wiring-bench",
    "DJ Trains": "dj-trains",
}
SKIP_NAMES = {".DS_Store"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.name not in SKIP_NAMES and not p.name.startswith("~$")
    }


def copy(src: Path, dst: Path, apply: bool, plan: list[str], label: str) -> None:
    plan.append(f"{label}: {dst}")
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="copy files instead of previewing")
    args = parser.parse_args()

    state = json.loads(STATE.read_text()) if STATE.is_file() else {}
    plan: list[str] = []
    conflicts: list[str] = []
    for desktop_rel, mirror_rel in PAIRS.items():
        left, right = DESKTOP / desktop_rel, MIRROR / mirror_rel
        if not left.is_dir():
            print(f"SKIP missing: {left}")
            continue
        for rel in sorted(files(left) | files(right)):
            a, b = left / rel, right / rel
            key = f"{mirror_rel}/{rel}"
            if not a.is_file():
                copy(b, a, args.apply, plan, "to Desktop")
                state[key] = digest(b)
                continue
            if not b.is_file():
                copy(a, b, args.apply, plan, "to mirror")
                state[key] = digest(a)
                continue
            ha, hb = digest(a), digest(b)
            if ha == hb:
                state[key] = ha
            elif state.get(key) == hb:
                copy(a, b, args.apply, plan, "to mirror")
                state[key] = ha
            elif state.get(key) == ha:
                copy(b, a, args.apply, plan, "to Desktop")
                state[key] = hb
            else:
                conflicts.append(key)

    for line in plan:
        print(line)
    for key in conflicts:
        print(f"CONFLICT: {key}")
    verb = "copied" if args.apply else "would copy"
    print(f"{verb} {len(plan)} file(s); {len(conflicts)} conflict(s)")
    if args.apply:
        STATE.write_text(json.dumps(state, indent=0, sort_keys=True))
    else:
        print("preview only; pass --apply to copy")
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
