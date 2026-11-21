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

`--wiring-only` writes the head and mast plan CSVs only (no publisher), from wiring.csv's wired heads. It never writes tables.xml, which is generated (ADR-029).
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables_build, wiring  # noqa: E402

ROOT = paths.REPO_ROOT
DATA = ROOT / "docs/wiring/signals"

SKIP_HEAD: set[str] = set()
SKIP_MAST: set[str] = set()

# Wired heads only (ADR-024, owner 2026-11-19): every other staging mast stands on internal heads
# (IH:HART:C1:<mast>, staging_masts.csv) until the owner wires it. The wired heads, their nodes and ports, are
# jmri/layouts/hart/data/wiring.csv's head rows (hartlib.wiring, the physical wiring source; owner 2026-11-20); add a
# head's row there when it is wired.
# Masts whose field build has fewer heads than the wiring plan: signal_mast_plan.csv keeps the planned heads;
# signal_head_plan.csv and the JMRI mast use only the fitted ones.
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
    planned = plan_masts(rows)
    with (DATA / "signal_head_plan.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=plan_fields, lineterminator="\n")
        w.writeheader()
        w.writerows(masts)

    # Enrich Digicon plan CSV with mqtt/packed/port columns (keep panel coords).
    plan_src = DATA / "signal_mast_plan.csv"
    if plan_src.exists():
        with plan_src.open(newline="") as f:
            old = list(csv.DictReader(f))
        by_name = {m["mast_user_name"]: m for m in planned}
        out_fields = list(old[0].keys())
        for col in (
            "heads",
            "mqtt_node",
            "parent_node_id",
            "packed_ids",
            "port_ids",
            "mast_system_name",
            "jmri_binding",
        ):
            if col not in out_fields:
                out_fields.append(col)
        enriched = []
        for row in old:
            name = row["proposed_mast_name"]
            if name in by_name:
                m = by_name[name]
                row = {
                    **row,
                    "heads": str(m["heads"]),
                    "mqtt_node": str(m["mqtt_node"]),
                    "parent_node_id": m["parent_node_id"],
                    "packed_ids": m["packed_ids"],
                    "port_ids": m["port_ids"],
                    "mast_system_name": m["mast_system_name"],
                    "jmri_binding": "virtual-heads+shsm",
                }
            enriched.append(row)
        with plan_src.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_fields, lineterminator="\n")
            w.writeheader()
            w.writerows(enriched)
        print(f"updated {plan_src}")

    print(f"wrote {DATA / 'signal_head_plan.csv'} ({len(masts)} masts)")


def _heads_xml(rows: list[dict]) -> str:
    parts = [
        '  <signalheads class="jmri.managers.configurexml.AbstractSignalHeadManagerXml">',
    ]
    for r in rows:
        parts.append(
            '    <signalhead class="jmri.implementation.configurexml.VirtualSignalHeadXml">'
        )
        parts.append(f"      <systemName>{r['system_name']}</systemName>")
        parts.append(f"      <userName>{r['user_name']}</userName>")
        parts.append("    </signalhead>")
    parts.append("  </signalheads>")
    return "\n".join(parts)


def _masts_xml(rows: list[dict]) -> str:
    parts = [
        '  <signalmasts class="jmri.managers.configurexml.DefaultSignalMastManagerXml">',
    ]
    seen = set()
    for r in rows:
        m = r["mast_user_name"]
        if m in SKIP_MAST or m in seen:
            continue
        seen.add(m)
        sysname = mast_system_name(m, rows).replace("&", "&amp;")
        parts.append(
            '    <signalmast class="jmri.implementation.configurexml.SignalHeadSignalMastXml">'
        )
        parts.append(f"      <systemName>{sysname}</systemName>")
        parts.append(f"      <userName>{m}</userName>")
        parts.append('      <unlit allowed="no" />')
        parts.append("    </signalmast>")
    parts.append("  </signalmasts>")
    return "\n".join(parts)


def check_live_heads(rows: list[dict], tables_text: str) -> list[str]:
    """Planned IH beans missing from tables.xml.

    IH numbers follow the wiring plan (tools/audit/check_wiring_crosswalk.py
    enforces it), so a plan that does not match live beans means the plan or
    tables.xml drifted and must not replace the tables block.
    """
    live = set(re.findall(r"<systemName>(IH\d+)</systemName>", tables_text))
    return sorted({r["system_name"] for r in rows} - live)


BLOCK_RE = re.compile(
    r"  <signalheads class=\"jmri\.managers\.configurexml\.AbstractSignalHeadManagerXml\">.*?"
    r"  </signalmasts>",
    re.S,
)


def lost_beans(block: str, tables_text: str) -> list[str]:
    """Head and mast system names in the live block that `block` would drop."""
    m = BLOCK_RE.search(tables_text)
    if not m:
        return []
    names = re.compile(r"<systemName>([^<]+)</systemName>")
    return sorted(set(names.findall(m.group(0))) - set(names.findall(block)))


def patch_tables(rows: list[dict]) -> None:
    """Refuse: tables.xml is generated (ADR-029, R9c), its heads and masts from devices.csv
    (build_staging_masts.py, tools/schematic/build_tables.py), so this script never writes it.
    The reason found is reported so --wiring-only is used instead.
    """
    rows = fitted_rows(rows)
    tables = paths.TABLES_XML
    text = tables.read_text()
    missing = check_live_heads(rows, text)
    if missing:
        raise SystemExit(
            "refusing to rewrite tables.xml: planned heads are not live beans "
            f"({len(missing)}: {', '.join(missing[:8])}). Run "
            "tools/audit/check_wiring_crosswalk.py. Use --wiring-only."
        )
    lost = lost_beans(_heads_xml(rows) + "\n" + _masts_xml(rows), text)
    dropped = f" ({len(lost)}: {', '.join(lost[:8])})" if lost else ""
    raise SystemExit(
        "refusing to rewrite tables.xml: the generated block would drop "
        f"live beans{dropped}, such as virtual masts and IH9990. "
        f"{tables_build.GENERATED_NOTE}. Use --wiring-only."
    )


def write_publisher(rows: list[dict]) -> None:
    """Publisher Digicon roster is dynamic (LCOS IH masts + MQTT enroll); no HEAD_NAMES rewrite."""
    path = ROOT / "jmri/scripts/signal_coordinator.py"
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    text = path.read_text()
    if "DigiconMqttSml()" not in text or "_enroll_packed" not in text:
        raise SystemExit(
            f"{path}: expected dynamic DigiconMqttSml() + _enroll_packed roster"
        )
    if "HEAD_NAMES_BEGIN" in text or "\nHEAD_NAMES =" in text:
        raise SystemExit(
            f"{path}: remove HEAD_NAMES; Digicon plants come from LCOS IH beans + MQTT"
        )
    print(
        f"publisher OK (dynamic Digicon roster; {len(rows)} wiring heads, "
        f"no HEAD_NAMES patch): {path.relative_to(ROOT)}"
    )



def main() -> int:
    wiring_only = "--wiring-only" in sys.argv
    if not wiring_only:
        paths.exit_if_overridden(Path(__file__).name)
    rows = build_rows()
    write_csvs(rows)
    if wiring_only:
        print("wiring-only: skipped inventory xlsx, tables.xml, publisher")
    else:
        print("the wiring inventory takes these ports: python3 tools/wiring/write_inventory.py")
        write_publisher(rows)
        patch_tables(rows)
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
