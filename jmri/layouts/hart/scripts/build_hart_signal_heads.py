#!/usr/bin/env python3
"""Build HART Digicon→JMRI virtual signal heads (LCOS packed MQTT numbers).

MQTT packed node == RF24 radio Address. Enclosure ID is C{Address} (D{Address}
for the helix DCC client). Never assign heads to D5 (radio 5, DCC).

Each physical searchlight disc is one 3-pin LCOS object (STOP/APPROACH/CLEAR =
R/Y/G on consecutive increasing ports). Two-head masts are two objects (T + B)
on the **same DNOU8** (6 pins)
so a module can sit next to its mast. A neighboring dwarf uses the leftover 2
pins; the 3rd dwarf pin spills to the adjacent cluster board when the plant
needs 9 pins. New 5V **OU4** on C1 / C4 / C13 (C12 and C11 use existing 5V OUs).

  radio 1  C1  Princess west (36 + 38). Packed 1xx.
  radio 2  C2  East End west overflow (24). Packed 2xx.
  radio 4  C4  Brick + Plane (motors Switch 1/3/5/13 on OU1). Packed 4xx.
  radio 11 C11 Princess east (40) + balloon (Mast 67/68). Packed 11xx.
  radio 12 C12 East End 34 + turnout motors 107–112. Packed 12xx.
  radio 13 C13 Barn. Packed 13xx.
  radio 3  C3  Motors 103–106 only — no Digicon heads.
  radio 5  D5  DCC only — no signal ports

It writes the head plan CSV (signal_head_plan.csv) from wiring.csv's wired heads (`--wiring-only`, the old flag, is still
accepted). It never writes tables.xml, which is generated (ADR-029); the full mode that refused to do so is gone.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict, cast

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, wiring  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402

ROOT = paths.REPO_ROOT
HEAD_PLAN = paths.SIGNAL_HEAD_PLAN


class HeadPlanError(ValueError):
    """wiring.csv's heads cannot be planned: a lamp on a calibration relay's port, two lamps on one port, a head
    without one R, one Y and one G lamp, or a mast with a head count no appearance is defined for."""


Disc = Literal["T", "B", "S"]
Lamp = Literal["R", "Y", "G"]

# Wired heads only (ADR-024): every other staging mast stands on internal heads (IH:HART:C1:<mast>, masts.csv)
# until it is wired. The wired heads, their nodes and ports, are jmri/layouts/hart/data/wiring.csv's head rows
# (hartlib.wiring, the physical wiring source); add a head's row there when it is wired. A mast with fewer
# wired heads than its mast rule gives it uses only the wired ones here; the planned heads stay the mast rule's.
# One 3-pin STOP/APPROACH/CLEAR object per physical disc. A 2-head mast owns
# 6 consecutive pins on one board (T then B). Packed = radio*100 + UID.
# disc: T top, B bottom, S single.
DISC_SORT: dict[str, int] = {"T": 0, "S": 1, "B": 2}
# Field pin order: R (Stop), Y (Approach), G (Clear) on consecutive increasing ports.
LAMPS: tuple[Lamp, ...] = ("R", "Y", "G")
APPEAR = {1: "one-searchlight", 2: "two-searchlight", 3: "SL-3-high"}
SYSTEM_BY_HEADS = {1: "basic", 2: "basic", 3: "AAR-1946"}


class WiredHead(NamedTuple):
    """One wired searchlight head (one LCOS signal object): its mast, node, packed number, the ports of its G, Y
    and R lamps, and its disc."""

    mast: str
    node: int
    parent: str
    packed: int
    g_port: str
    y_port: str
    r_port: str
    disc: Disc


class HeadPin(NamedTuple):
    """One lamp pin of a wired head: a row of build_rows."""

    mast: str
    node: int
    parent: str
    packed: int
    disc: Disc
    color: Lamp
    port: str

    @property
    def system_name(self) -> str:
        return f"IH{self.packed}"


class PlanRow(TypedDict):
    """One row of signal_head_plan.csv (PLAN_FIELDS)."""

    mast_user_name: str
    mqtt_node: int
    parent_node_id: str
    heads: int
    appearance: str
    physignal: str
    mast_system_name: str
    head_system_names: str
    packed_ids: str
    port_ids: str


def heads_3pin(path: Path | None = None) -> list[WiredHead]:
    """Each wired head of wiring.csv `path` (hartlib.wiring.digicon_rows), in the order of its first lamp row.
    HeadPlanError on a head without exactly one R, one Y and one G lamp, or with a disc other than T, B or S."""
    pins: dict[int, dict[str, dict[str, str]]] = {}
    for r in wiring.digicon_rows(path):
        lamps = pins.setdefault(int(r["packed"]), {})
        if r["lamp_color"] in lamps:
            raise HeadPlanError(f"head IH{r['packed']} ({r['mast_user_name']}) has two {r['lamp_color']} lamps")
        lamps[r["lamp_color"]] = r
    out = []
    for packed_id, lamp in pins.items():
        if sorted(lamp) != sorted(LAMPS):
            raise HeadPlanError(f"head IH{packed_id} has lamps {sorted(lamp)}, not one each of {list(LAMPS)}")
        r = lamp["R"]
        disc = r["disc_role"]
        if disc not in DISC_SORT:
            raise HeadPlanError(f"head IH{packed_id} ({r['mast_user_name']}) has disc {disc!r}, not one of "
                                f"{list(DISC_SORT)}")
        out.append(WiredHead(r["mast_user_name"], int(r["mqtt_node"]), r["parent_node_id"], packed_id,
                             lamp["G"]["port_id"], lamp["Y"]["port_id"], r["port_id"], cast(Disc, disc)))
    return out


def discs_of(mast: str, rows: list[HeadPin]) -> list[HeadPin]:
    """The first pin of each of the mast's heads, top disc first and bottom last."""
    by_packed: dict[int, HeadPin] = {}
    for r in rows:
        if r.mast == mast:
            by_packed.setdefault(r.packed, r)
    return sorted(by_packed.values(), key=lambda r: DISC_SORT[r.disc])


def build_rows(path: Path | None = None) -> list[HeadPin]:
    """The pin rows of the wired heads (heads_3pin, from wiring.csv `path`), R, Y, G per head. HeadPlanError on a
    lamp on a calibration relay's port or two lamps on one port."""
    rows: list[HeadPin] = []
    seen_ports: dict[str, str] = {}
    # The calibration relays' ports (wiring.csv's calibration rows: the relay that resets the DCC power so a node's
    # block detectors calibrate, one on every node with detectors) are never a lamp.
    cal_ports = wiring.calibration_ports(path)
    for head in heads_3pin(path):
        ports = {"G": head.g_port, "Y": head.y_port, "R": head.r_port}
        for color in LAMPS:
            port = ports[color]
            if port in cal_ports:
                raise HeadPlanError(
                    f"{port} is a calibration relay's port (wiring.csv); "
                    f"cannot assign {head.mast} {head.disc} {color}"
                )
            if port in seen_ports:
                raise HeadPlanError(f"duplicate port {port}: {seen_ports[port]} and {head.mast}")
            seen_ports[port] = f"{head.mast} {head.disc} {color}"
            rows.append(HeadPin(head.mast, head.node, head.parent, head.packed, head.disc, color, port))
    return rows


def plan_masts(rows: list[HeadPin]) -> list[PlanRow]:
    """One signal_head_plan row per mast, in the order of each mast's first pin. HeadPlanError on a mast whose
    head count has no appearance (APPEAR)."""
    by_mast: dict[str, list[HeadPin]] = {}
    for r in rows:
        by_mast.setdefault(r.mast, []).append(r)
    masts: list[PlanRow] = []
    for m, pins in by_mast.items():
        discs = discs_of(m, pins)
        n = len(discs)
        if n not in APPEAR:
            raise HeadPlanError(f"{m} has {n} wired heads; an appearance is defined for {sorted(APPEAR)} heads only")
        masts.append(
            {
                "mast_user_name": m,
                "mqtt_node": pins[0].node,
                "parent_node_id": pins[0].parent,
                "heads": n,
                "appearance": APPEAR[n],
                "physignal": "double" if n == 2 else "single",
                "mast_system_name": mast_system_name(discs),
                "head_system_names": " ".join(d.system_name for d in discs),
                "packed_ids": " ".join(str(d.packed) for d in discs),
                "port_ids": " ".join(x.port for x in pins),
            }
        )
    return masts


def mast_system_name(discs: list[HeadPin]) -> str:
    """The signal mast system name of a mast with these heads (discs_of, one pin per head)."""
    n = len(discs)
    ihs = "".join(f"({d.system_name})" for d in discs)
    return f"IF$shsm:{SYSTEM_BY_HEADS[n]}:{APPEAR[n]}{ihs}"


PLAN_FIELDS = [
    "mast_user_name",
    "mqtt_node",
    "parent_node_id",
    "heads",
    "appearance",
    "physignal",
    "mast_system_name",
    "head_system_names",
    "packed_ids",
    "port_ids",
]


def head_plan_text(rows: list[HeadPin]) -> tuple[str, int]:
    """The head plan CSV text for the given head rows, and its mast count."""
    masts = plan_masts(rows)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=PLAN_FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(masts)
    return out.getvalue(), len(masts)


def write_csvs(rows: list[HeadPin]) -> None:
    HEAD_PLAN.parent.mkdir(parents=True, exist_ok=True)
    text, count = head_plan_text(rows)
    with HEAD_PLAN.open("w", newline="", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {HEAD_PLAN} ({count} masts)")


def check_csvs(rows: list[HeadPin]) -> bool:
    """True when the committed head plan is what wiring.csv gives now (compared in memory, nothing written)."""
    text, _ = head_plan_text(rows)
    current = HEAD_PLAN.read_bytes().decode("utf-8") if HEAD_PLAN.is_file() else None
    return current == text


def main() -> int:
    """Write signal_head_plan.csv from wiring.csv's wired heads. `--wiring-only`, the old
    name of this one mode, is still accepted. `--check` writes nothing: it exits 1 when the file is stale."""
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("--wiring-only", action="store_true", help="the only mode; accepted for old callers")
    ap.add_argument("--check", action="store_true", help="exit 1 when signal_head_plan.csv is stale; write nothing")
    args = ap.parse_args()
    try:
        rows = build_rows()
        plan_masts(rows)            # a head count with no appearance stops here, before anything is written
    except (FactsError, HeadPlanError) as exc:
        print(f"build_hart_signal_heads.py: {exc}", file=sys.stderr)
        return 2
    if args.check:
        if check_csvs(rows):
            print(f"{HEAD_PLAN.name}: current")
            return 0
        print(f"{HEAD_PLAN} is stale: run python3 jmri/layouts/hart/scripts/build_hart_signal_heads.py "
              "--wiring-only (make panels does)", file=sys.stderr)
        return 1
    write_csvs(rows)
    by: dict[int, list[HeadPin]] = {}
    for r in rows:
        by.setdefault(r.node, []).append(r)
    for node in sorted(by):
        pins = by[node]
        masts = {p.mast for p in pins}
        print(
            f"node {node} {pins[0].parent}: {len(masts)} heads / {len(pins)} pins "
            f"packed {sorted({p.packed for p in pins})}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
