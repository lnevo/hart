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

import csv
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, wiring  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402

ROOT = paths.REPO_ROOT
DATA = ROOT / "docs/wiring/signals"

SKIP_MAST: set[str] = set()

# Wired heads only (ADR-024, owner 2026-11-19): every other staging mast stands on internal heads
# (IH:HART:C1:<mast>, staging_masts.csv) until the owner wires it. The wired heads, their nodes and ports, are
# jmri/layouts/hart/data/wiring.csv's head rows (hartlib.wiring, the physical wiring source; owner 2026-11-20); add a
# head's row there when it is wired.
# Masts whose field build has fewer heads than the mast rule gives them: signal_head_plan.csv and the JMRI mast use
# only the fitted ones; the planned heads stay the mast rule's (staging_masts.csv, ADR-024).
FITTED_HEADS: dict[str, set[int]] = {}
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

# The calibration relays' ports (wiring.csv's calibration rows: the relay that resets the DCC power so a node's
# block detectors calibrate, one on every node with detectors; owner 2026-11-21): never a lamp.


def packed(node: int, signal_index: int) -> int:
    return node * 100 + 32 + signal_index


def discs_of(mast: str, rows: list[dict]) -> list[dict]:
    by_packed: dict[int, dict] = {}
    for r in rows:
        if r["mast_user_name"] == mast:
            by_packed.setdefault(r["packed"], r)
    discs = list(by_packed.values())
    discs.sort(key=lambda r: DISC_SORT.get(r["disc_role"], 9))
    return discs


def build_rows(path: Path | None = None) -> list[dict]:
    """The pin rows of the wired heads (heads_3pin, from wiring.csv `path`). SystemExit on a lamp on a calibration
    relay's port or two lamps on one port."""
    rows: list[dict] = []
    seen_ports: dict[str, str] = {}
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
                raise SystemExit(
                    f"{port} is a calibration relay's port (wiring.csv); "
                    f"cannot assign {mast} {disc} {color}"
                )
            if port in seen_ports:
                raise SystemExit(f"duplicate port {port}: {seen_ports[port]} and {mast}")
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


def fitted_rows(rows: list[dict]) -> list[dict]:
    """Rows for heads actually fitted in the field (see FITTED_HEADS)."""
    return [
        r
        for r in rows
        if r["mast_user_name"] not in FITTED_HEADS
        or r["packed"] in FITTED_HEADS[r["mast_user_name"]]
    ]


def plan_masts(rows: list[dict]) -> list[dict]:
    """One signal_head_plan row per mast, from the given head rows."""
    masts = []
    seen = set()
    for r in rows:
        m = r["mast_user_name"]
        if m in SKIP_MAST or m in seen:
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


def write_csvs(rows: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    plan_fields = [
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
    masts = plan_masts(fitted_rows(rows))
    with (DATA / "signal_head_plan.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=plan_fields, lineterminator="\n")
        w.writeheader()
        w.writerows(masts)

    print(f"wrote {DATA / 'signal_head_plan.csv'} ({len(masts)} masts)")


def main() -> int:
    """Write signal_head_plan.csv from wiring.csv's wired heads. `--wiring-only`, the old
    name of this one mode, is still accepted."""
    try:
        rows = build_rows()
    except FactsError as exc:
        print(f"build_hart_signal_heads.py: {exc}", file=sys.stderr)
        return 2
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
