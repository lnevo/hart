#!/usr/bin/env python3
"""Copy live pipeline guides into consolidation/wiki/pipelines/ with SoR header."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "wiki/pipelines"
OUT = ROOT / "consolidation/wiki/pipelines"

SOR_HEADER = """> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record (consolidation view)

| Kind | Live path (read-only) | Proposed consolidation path |
|------|----------------------|----------------------------|
| Runbook | `wiki/pipelines/{name}` | `consolidation/wiki/pipelines/{name}` |
| Artifacts | See live guide below | `consolidation/sor/` when authoritative |

---

"""

SKIP = {"lcos-bom.md"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for src in sorted(LIVE.glob("*.md")):
        if src.name in SKIP or src.name == "README.md":
            continue
        text = src.read_text(encoding="utf-8")
        if "Consolidation draft" in text:
            body = text
        else:
            body = SOR_HEADER.format(name=src.name) + text
        (OUT / src.name).write_text(body, encoding="utf-8")
        print(f"Wrote {OUT / src.name}")

    # Consolidation-specific README
    readme = """# Pipeline guides (consolidation drafts)

Draft copies of live [`wiki/pipelines/`](../../../wiki/pipelines/) with SoR tables.

Open the [browse portal](../../index.html) for HTML navigation.

| # | Guide |
|---|-------|
"""
    for src in sorted(LIVE.glob("*.md")):
        if src.name in SKIP or src.name == "README.md":
            continue
        m = re.search(r"Pipeline (\d+)", src.read_text(encoding="utf-8")[:200])
        num = m.group(1) if m else "?"
        readme += f"| {num} | [{src.stem}]({src.name}) |\n"

    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"Wrote {OUT / 'README.md'}")


if __name__ == "__main__":
    main()
