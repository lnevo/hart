#!/usr/bin/env python3
"""Set the window size a JMRI profile remembers for each Layout Editor panel to the size tables.xml gives it.

    python3 tools/hosts/panel_window_sizes.py USER_INTERFACE_XML [--tables PATH] [--check] [--backup]

hartlib.jmri_profile does the edit; its docstring says what changes and what stays. Run it with JMRI closed: JMRI
rewrites the file when a window moves and when it quits. Every deploy runs it on the hosts after it installs
tables.xml (tools/hosts/pi/apply_hart_package_local.sh, tools/hosts/windows/apply_hart_package_local.ps1), from
cats/scripts/ in the package with the part of hartlib it needs (tools/hosts/deploy/stage.sh).

--check: change nothing; exit 1 when a saved size differs from the tables'.
--backup: before writing, keep the file as it was in <file>.hart-<stamp>.bak beside it; the newest 5 copies are kept.
Nothing is written, and no copy kept, when every size already matches.
Exit 2, with the reason on stderr, when a file cannot be read or written.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import jmri_profile  # noqa: E402


def _repo_tables() -> Path:
    # hartlib.paths needs a checkout; a host package has none and always passes --tables.
    from hartlib import paths
    return paths.REPO_TABLES_XML


def run(user_interface: Path, tables: Path, *, check: bool = False, backup: bool = False) -> int:
    """Set the sizes and print what changed: 0 done or nothing to do, 1 a size differs under `check`."""
    sizes = jmri_profile.panel_sizes(tables)
    text = jmri_profile.read_user_interface(user_interface)
    new, changes = jmri_profile.resize(text, sizes)
    saved = set(jmri_profile.saved_windows(text))
    for name in sorted(sizes):
        if name not in saved:
            print(f"{name}: no saved window (JMRI opens it at the tables' size)")
    for change in changes:
        print(f"{change.panel}: {change.before} -> {change.after}")
    if not changes:
        print("every saved panel window already has the tables' size")
        return 0
    if check:
        return 1
    copy = jmri_profile.write_user_interface(user_interface, new, backup=backup)
    print(f"wrote {user_interface}" + (f"; its previous copy is {copy}" if copy else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("user_interface", type=Path, help="the profile's user-interface.xml")
    ap.add_argument("--tables", type=Path, help="tables.xml (default: this checkout's)")
    ap.add_argument("--check", action="store_true", help="change nothing; exit 1 when a size differs")
    ap.add_argument("--backup", action="store_true", help="keep the file as it was in <file>.hart-<stamp>.bak")
    args = ap.parse_args(argv)
    try:
        return run(args.user_interface, args.tables or _repo_tables(), check=args.check, backup=args.backup)
    except jmri_profile.WindowSizesError as exc:
        print(f"panel_window_sizes: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
