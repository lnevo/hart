#!/usr/bin/env python3
"""Audit consolidation path configuration — runtime vs mirror sources."""
from __future__ import annotations

import re
import sys
from pathlib import Path

CON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CON / "scripts" / "lib"))

from consolidation_paths import (  # noqa: E402
    all_mirror_sources,
    all_runtime_paths,
    consolidation_root,
    sts_compose_files,
)


def under_consolidation(path: Path, con: Path) -> bool:
    try:
        path.resolve().relative_to(con.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    con = consolidation_root()
    print("=== Consolidation path audit ===")
    print(f"CONSOLIDATION_ROOT: {con}")
    print()

    fail = 0
    print("Runtime paths (should live under consolidation/):")
    for name, path in all_runtime_paths().items():
        ok = under_consolidation(path, con) or name == "HART_REPO_ROOT"
        status = "OK" if ok else "WARN"
        if not ok:
            fail += 1
        print(f"  {status} {name}={path}")

    print()
    print("Mirror sources (may point at live ~/sts, ~/Desktop/HART — read-only):")
    for name, path in all_mirror_sources().items():
        print(f"  SRC {name}={path}")

    print()
    print("STS Docker compose:")
    compose = sts_compose_files()[0]
    print(f"  {compose}")
    if not compose.is_file():
        print("  WARN missing — run: bash consolidation/scripts/refresh_sts_docker_compose.sh")
        fail += 1
    else:
        text = compose.read_text(encoding="utf-8")
        if "${" in text or "@STS_" in text:
            print("  WARN compose has unresolved placeholders — run refresh_sts_docker_compose.sh")
            fail += 1
        elif "~/sts" in text or "$HOME/sts" in text:
            print("  WARN compose still references ~/sts")
            fail += 1
        else:
            print("  OK literal bind paths (no compose env substitution)")
        data_root = con / "external/sts-docker-data"
        for line in text.splitlines():
            m = re.match(r'^\s*-\s*(?:"([^"]+)|([^:\s]+)):/var/', line)
            if not m:
                continue
            host = m.group(1) or m.group(2)
            if not under_consolidation(Path(host), con):
                print(f"  WARN bind outside consolidation: {host}")
                fail += 1

    print()
    if fail:
        print(f"FAILED: {fail} issue(s)")
        return 1
    print("PASS: runtime paths resolve under consolidation workspace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
