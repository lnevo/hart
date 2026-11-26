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

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, wiring  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402

ROOT = paths.REPO_ROOT
HEAD_PLAN = paths.SIGNAL_HEAD_PLAN


class HeadPlanError(ValueError):
    """wiring.csv puts a lamp on a calibration relay's port, or two lamps on one port."""


# Wired heads only (ADR-024): every other staging mast stands on internal heads (IH:HART:C1:<mast>, masts.csv)
# until it is wired. The wired heads, their nodes and ports, are jmri/layouts/hart/data/wiring.csv's head rows
# (hartlib.wiring, the physical wiring source); add a head's row there when it is wired. A mast with fewer
# wired heads than its mast rule gives it uses only the wired ones here; the planned heads stay the mast rule's.
# One 3-pin STOP/APPROACH/CLEAR object per physical disc. A 2-head mast owns
# 6 consecutive pins on one board (T then B). Packed = radio*100 + UID.
# disc: T top, B bottom, S single.
# Field pin order is R (Stop), Y (Approach), G (Clear) — Port A/B/C on
# consecutive increasing LCOS ports.


def heads_3pin(path: Path | None = None) -> list[tuple[str, int, str, str, int, str, str, str, str, str]]:
    """(mast, node, parent, location, packed, g port, y port, r port, disc, was) of each wired head, from
    wiring.csv (hartlib.wiring.digicon_rows); location and was are left blank (history only)."""
    pins: dict[int, dict[str, dict]] = {}
    for r in wiring.digicon_rows(path):
        pins.setdefault(int(r["packed"]), {})[r["lamp_color"]] = r
    out = []
    for packed_id, lamp in pins.items():
        r = lamp["R"]
        out.append((r["mast_user_name"], int(r["mqtt_node"]), r["parent_node_id"], "", packed_id,
                    lamp["G"]["port_id"], lamp["Y"]["port_id"], r["port_id"], r["disc_role"], ""))
    return out


APPEAR = {1: "one-searchlight", 2: "two-searchlight", 3: "SL-3-high"}
SYSTEM_BY_HEADS = {1: "basic", 2: "basic", 3: "AAR-1946"}
DISC_SORT = {"T": 0, "S": 1, "B": 2}

PIN_ORDER = (("R", "r_port"), ("Y", "y_port"), ("G", "g_port"))


def discs_of(mast: str, rows: list[dict]) -> list[dict]:
    by_packed: dict[int, dict] = {}
    for r in rows:
        if r["mast_user_name"] == mast:
            by_packed.setdefault(r["packed"], r)
    discs = list(by_packed.values())
    discs.sort(key=lambda r: DISC_SORT.get(r["disc_role"], 9))
    return discs


def build_rows(path: Path | None = None) -> list[dict]:
    """The pin rows of the wired heads (heads_3pin, from wiring.csv `path`). HeadPlanError on a lamp on a calibration
    relay's port or two lamps on one port."""
    rows: list[dict] = []
    seen_ports: dict[str, str] = {}
    # The calibration relays' ports (wiring.csv's calibration rows: the relay that resets the DCC power so a node's
    # block detectors calibrate, one on every node with detectors) are never a lamp.
    cal_ports = wiring.calibration_ports(path)
    for mast, node, parent, loc, pid, g, y, r, disc, was in heads_3pin(path):
        uid = pid - node * 100
        idx = uid - 32
        short = mast[5:] if mast.startswith("Mast ") else mast
        ports = {"G": g, "Y": y, "R": r}
        label = f"{short} {disc}" if disc in ("T", "B") else short
        for color, _key in PIN_ORDER:
            port = ports[color]
            if port in cal_ports:
                raise HeadPlanError(
                    f"{port} is a calibration relay's port (wiring.csv); "
                    f"cannot assign {mast} {disc} {color}"
                )
            if port in seen_ports:
                raise HeadPlanError(f"duplicate port {port}: {seen_ports[port]} and {mast}")
            seen_ports[port] = f"{mast} {disc} {color}"
            rows.append(
                {
                    "mqtt_node": node,
                    "parent_node_id": parent,
                    "board_location": loc,
                    "signal_index": idx,
                    "uid": uid,
                    "packed": pid,
                    "system_name": f"IH{pid}",
                    "user_name": f"Head {label} {color}",
                    "mast_user_name": mast,
                    "disc_role": disc,
                    "head_role": disc,
                    "lamp_color": color,
                    "port_id": port,
                    "g_port": g,
                    "y_port": y,
                    "r_port": r,
                    "lcos_recipe": "STOP/APPROACH/CLEAR",
                    "topic": f"track/signalhead/{pid}",
                }
            )
    return rows


def plan_masts(rows: list[dict]) -> list[dict]:
    """One signal_head_plan row per mast, from the given head rows."""
    masts = []
    seen = set()
    for r in rows:
        m = r["mast_user_name"]
        if m in seen:
            continue
        seen.add(m)
        hs = [x for x in rows if x["mast_user_name"] == m]
        discs = discs_of(m, rows)
        n = len(discs)
        masts.append(
            {
                "mast_user_name": m,
                "mqtt_node": r["mqtt_node"],
                "parent_node_id": r["parent_node_id"],
                "heads": n,
                "appearance": APPEAR[n],
                "physignal": "double" if n == 2 else "single",
                "mast_system_name": mast_system_name(m, rows),
                "head_system_names": " ".join(d["system_name"] for d in discs),
                "packed_ids": " ".join(str(d["packed"]) for d in discs),
                "port_ids": " ".join(x["port_id"] for x in hs),
            }
        )
    return masts


def mast_system_name(mast: str, rows: list[dict]) -> str:
    discs = discs_of(mast, rows)
    n = len(discs)
    ihs = "".join(f"({d['system_name']})" for d in discs)
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


def head_plan_text(rows: list[dict]) -> tuple[str, int]:
    """The head plan CSV text for the given head rows, and its mast count."""
    masts = plan_masts(rows)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=PLAN_FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(masts)
    return out.getvalue(), len(masts)


def write_csvs(rows: list[dict]) -> None:
    HEAD_PLAN.parent.mkdir(parents=True, exist_ok=True)
    text, count = head_plan_text(rows)
    with HEAD_PLAN.open("w", newline="", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {HEAD_PLAN} ({count} masts)")


def check_csvs(rows: list[dict]) -> bool:
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
    by: dict[int, list] = {}
    for r in rows:
        by.setdefault(r["mqtt_node"], []).append(r)
    for node in sorted(by):
        pins = by[node]
        masts = {p["mast_user_name"] for p in pins}
        print(
            f"node {node} {pins[0]['parent_node_id']}: {len(masts)} heads / {len(pins)} pins "
            f"packed {sorted({p['packed'] for p in pins})}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
