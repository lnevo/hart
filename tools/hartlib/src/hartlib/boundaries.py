"""le_signal_boundaries.csv: where each staging mast stands on the generated Layout Editor panel, by the turnout or
anchor ident and the slot it binds in. One reader for every script that binds or checks masts by slot:
tools/schematic/le_checks.py (check_boundaries, the LE build), jmri/layouts/hart/scripts/audit_panel_contracts.py
(load_boundaries, check.sh and the deploy audit) and jmri/layouts/hart/scripts/apply_le_sml_facing.py
(load_assignments, which writes the masts into tables.xml). A column or slot rule changes here only.

Columns: kind (turnout or anchor), ident, slot (A to D on a turnout, east or west on an anchor), mast_user_name and
notes. Every value is read stripped, and a slot in either case is stored as A to D or east/west. read() stops on an unknown kind, a slot its kind has no such slot for, a mast
named twice, or two masts in one slot.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from . import paths

PATH = paths.LAYOUT_DATA / "le_signal_boundaries.csv"
COLUMNS = ("kind", "ident", "slot", "mast_user_name", "notes")
SLOTS = {"turnout": ("A", "B", "C", "D"), "anchor": ("east", "west")}


@dataclass(frozen=True)
class Boundary:
    kind: str
    ident: str
    slot: str
    mast: str
    notes: str = ""

    @property
    def binding_name(self) -> str:
        """The panel attribute that binds this mast: signalCMast on a turnout's leg C, eastboundsignalmast on an
        anchor's east side."""
        if self.kind == "turnout":
            return f"signal{self.slot.upper()}Mast"
        return f"{self.slot.lower()}boundsignalmast"


def read(path: Path = PATH) -> list[Boundary]:
    """The file's rows in order, each value stripped. Raises ValueError naming the path and the row's mast on any
    row that breaks the module's rules."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in COLUMNS[:4] if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns {', '.join(missing)}")
        rows = list(reader)
    out, masts, slots, bad = [], set(), set(), []
    for row in rows:
        kind, slot = (row["kind"] or "").strip(), (row["slot"] or "").strip()
        slot = slot.upper() if kind == "turnout" else slot.lower()
        b = Boundary(kind=kind, ident=(row["ident"] or "").strip(), slot=slot,
                     mast=(row["mast_user_name"] or "").strip(), notes=(row.get("notes") or "").strip())
        if b.kind not in SLOTS:
            bad.append(f"{b.mast or '<no mast>'}: unknown kind {b.kind!r} (turnout or anchor)")
        elif b.slot not in SLOTS[b.kind]:
            bad.append(f"{b.mast or '<no mast>'}: {b.kind} {b.ident} has no slot {b.slot!r} "
                       f"({', '.join(SLOTS[b.kind])})")
        if not b.mast or not b.ident:
            bad.append(f"{b.mast or '<no mast>'}: no mast name or no ident")
            continue
        if b.mast in masts:
            bad.append(f"{b.mast}: named twice")
        if (b.kind, b.ident, b.slot) in slots:
            bad.append(f"{b.mast}: {b.kind} {b.ident} slot {b.slot} already holds another mast")
        masts.add(b.mast)
        slots.add((b.kind, b.ident, b.slot))
        out.append(b)
    if bad:
        raise ValueError(f"{path}: " + "; ".join(bad))
    return out
