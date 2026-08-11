#!/usr/bin/env python3
"""Build HART Digicon→JMRI virtual signal heads (LCOS packed MQTT numbers).

Allocation (MQTT display node = radio addr octal-digits-as-decimal):
  node 4  — Brick W-1/W-2 + both Plane faces (leave Brick East Main West / 464 alone)
  node 13 — Barn / West Yard 117–117b  (radio 013 → display 13)
  node 12 — East End                 (radio 012 → display 12)
  node 1  — Princess                 (radio 1   → display 1)

Each physical lamp = one LCOS signal UID (32+index) → packed = node*100 + uid.
Writes:
  cats/data/signal_wiring.csv
  cats/data/signal_head_plan.csv
  patches tables/new_tables.xml + hart output tables/hart_prod/pi_tables
  regenerates cats-virtual-3 appearance + aspects.xml appearancefiles
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATS_MASTS = ROOT / "cats/resources/signals/cats-masts"
DATA = ROOT / "cats/data"

# (mast_userName, heads, mqtt_node, digicon_lamp) — heads count 1/2/3
# Order within a node = signal_index assignment (top→bottom / high→low).
MASTS: list[tuple[str, int, int, str]] = [
    # node 4 — Plane + W-Y stubs (not Brick East Main West)
    ("Plane East East Main Ext", 2, 4, "double"),
    ("Plane East OS 102", 2, 4, "double"),
    ("Brick West Yard 1", 1, 4, "single"),
    ("Brick West Yard 2", 1, 4, "single"),
    # node 13 — Barn
    ("West Yard West OS 117", 2, 13, "double"),
    ("West Yard East Yard T6", 1, 13, "single"),
    ("West Yard West East Main Ext", 2, 13, "double"),
    ("West Yard East OS 117b", 2, 13, "double"),
    # node 12 — East End
    ("East End West Main West", 2, 12, "double"),
    ("East End East OS 111a", 2, 12, "double"),
    ("East End West Yard Track 1", 1, 12, "single"),
    ("East End East Lead", 2, 12, "double"),
    ("East End South OS 110", 1, 12, "single"),
    ("East End South OS 112", 2, 12, "double"),
    # node 1 — Princess
    ("Princess North McKees Rocks", 3, 1, "triple"),
    ("Princess West OS 113b", 2, 1, "double"),
    ("Princess West OS 113a", 2, 1, "double"),
    ("Princess South McKeesport", 3, 1, "triple"),
]

ROLE = {1: ("",), 2: ("T", "B"), 3: ("T", "M", "B")}
ROLE_NAME = {"": "", "T": " Top", "M": " Middle", "B": " Bottom"}

# Appearance map name inside cats-masts (must match appearance-*.xml file stem suffix)
APPEAR = {1: "cats-virtual", 2: "cats-virtual-2", 3: "cats-virtual-3"}

# DNOU8 Parent Node ID + board for each MQTT display node (LCOS inventory v48).
# mqtt 13 ← RF24/LCOS 11 (%o → "13"); hardware Parent Node C1 (Helix Lower).
# mqtt 12 ← radio "012" (East End); hardware Parent Node C7 (North Upper, sheet addr 12).
# mqtt 4  ← C4 West Lower; mqtt 1 ← D1 (Princess — OU boards added for Digicon).
NODE_PORTS: dict[int, list[str]] = {
    4: [f"C4-OU2-{i}" for i in range(1, 7)],  # 6 heads
    13: [f"C1-OU2-{i}" for i in range(1, 7)] + ["C1-OU3-1"],  # 7 heads
    12: [f"C7-OU2-{i}" for i in range(1, 7)] + [f"C7-OU3-{i}" for i in range(1, 5)],  # 10
    1: [f"D1-OU2-{i}" for i in range(1, 9)] + [f"D1-OU3-{i}" for i in range(1, 3)],  # 10
}
NODE_BOARD_LOC: dict[int, str] = {
    4: "West - Lower",
    13: "Helix - Lower (Barn / West Yard)",
    12: "North - Upper (East End)",
    1: "Princess / Helix DCC node",
}
NODE_PARENT: dict[int, str] = {4: "C4", 13: "C1", 12: "C7", 1: "D1"}


def packed(node: int, signal_index: int) -> int:
    return node * 100 + 32 + signal_index


def build_rows() -> list[dict]:
    per_node: dict[int, int] = {}
    rows: list[dict] = []
    for mast, nheads, node, lamp in MASTS:
        roles = ROLE[nheads]
        ports = NODE_PORTS[node]
        for role in roles:
            idx = per_node.get(node, 0)
            per_node[node] = idx + 1
            if idx >= len(ports):
                raise SystemExit(f"node {node}: need port for signal_index {idx}")
            pid = packed(node, idx)
            rows.append(
                {
                    "mqtt_node": node,
                    "parent_node_id": NODE_PARENT[node],
                    "board_location": NODE_BOARD_LOC[node],
                    "signal_index": idx,
                    "uid": 32 + idx,
                    "packed": pid,
                    "system_name": f"IH{pid}",
                    "user_name": f"{mast}{ROLE_NAME[role]}".strip(),
                    "mast_user_name": mast,
                    "head_role": role or "S",
                    "heads": nheads,
                    "appearance": APPEAR[nheads],
                    "physignal": lamp,
                    "port_id": ports[idx],
                    "topic": f"track/signalhead/IH{pid}",
                }
            )
    return rows


def mast_system_name(mast: str, rows: list[dict]) -> str:
    heads = [r for r in rows if r["mast_user_name"] == mast]
    n = heads[0]["heads"]
    appear = heads[0]["appearance"]
    ids = "".join(f"({r['system_name']})" for r in heads)
    return f"IF$shsm:cats-masts:{appear}{ids}"


def write_csvs(rows: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    wiring_fields = [
        "port_id",
        "parent_node_id",
        "mqtt_node",
        "board_location",
        "signal_index",
        "uid",
        "packed",
        "system_name",
        "user_name",
        "mast_user_name",
        "head_role",
        "topic",
        "device_type",
        "voltage_rail",
        "notes",
    ]
    with (DATA / "signal_wiring.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=wiring_fields)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    **{k: r[k] for k in wiring_fields if k in r},
                    "device_type": "Searchlight Signal Head",
                    "voltage_rail": "5V",
                    "notes": (
                        f"LCOS Signal {r['signal_index']} UID {r['uid']}; "
                        f"Digicon mast '{r['mast_user_name']}'"
                    ),
                }
            )

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
    masts = []
    seen = set()
    for r in rows:
        m = r["mast_user_name"]
        if m in seen:
            continue
        seen.add(m)
        hs = [x for x in rows if x["mast_user_name"] == m]
        masts.append(
            {
                "mast_user_name": m,
                "mqtt_node": r["mqtt_node"],
                "parent_node_id": r["parent_node_id"],
                "heads": r["heads"],
                "appearance": r["appearance"],
                "physignal": r["physignal"],
                "mast_system_name": mast_system_name(m, rows),
                "head_system_names": " ".join(x["system_name"] for x in hs),
                "packed_ids": " ".join(str(x["packed"]) for x in hs),
                "port_ids": " ".join(x["port_id"] for x in hs),
            }
        )
    with (DATA / "signal_head_plan.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=plan_fields)
        w.writeheader()
        w.writerows(masts)

    # Enrich Digicon plan CSV with mqtt/packed/port columns (keep panel coords).
    plan_src = DATA / "signal_mast_plan.csv"
    if plan_src.exists():
        with plan_src.open(newline="") as f:
            old = list(csv.DictReader(f))
        by_name = {m["mast_user_name"]: m for m in masts}
        out_fields = list(old[0].keys())
        for col in (
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
            if name == "Brick East Main West":
                row = {
                    **row,
                    "mqtt_node": "4",
                    "parent_node_id": "C4",
                    "packed_ids": "464",
                    "port_ids": "",
                    "mast_system_name": "IF$mqm:AAR-1946:SL-1-high-abs($464)",
                    "jmri_binding": "mqtt-mast",
                }
            elif name in by_name:
                m = by_name[name]
                row = {
                    **row,
                    "mqtt_node": str(m["mqtt_node"]),
                    "parent_node_id": m["parent_node_id"],
                    "packed_ids": m["packed_ids"],
                    "port_ids": m["port_ids"],
                    "mast_system_name": m["mast_system_name"],
                    "jmri_binding": "virtual-heads+shsm",
                }
            enriched.append(row)
        with plan_src.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=out_fields)
            w.writeheader()
            w.writerows(enriched)
        print(f"updated {plan_src}")

    print(f"wrote {DATA / 'signal_wiring.csv'} ({len(rows)} heads)")
    print(f"wrote {DATA / 'signal_head_plan.csv'} ({len(masts)} masts)")


def update_lcos_inventory(rows: list[dict]) -> None:
    """Rewrite Digicon signal ports on LCOS_Layout_Inventory_v48 DNOU8 sheet."""
    inv = Path.home() / "Downloads" / "LCOS_Layout_Inventory_v48.xlsx"
    if not inv.exists():
        print(f"skip inventory update (missing {inv})")
        return
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("skip inventory update (openpyxl not installed)")
        return
    wb = load_workbook(inv)
    ws = wb["DNOU8"]
    # Map existing rows by Output Port ID (col A)
    by_port: dict[str, int] = {}
    for i, row in enumerate(ws.iter_rows(min_row=2), start=2):
        pid = row[0].value
        if pid:
            by_port[str(pid)] = i
    assigned = {r["port_id"] for r in rows}
    # Clear old dwarf labels on ports we are reclaiming (leave unrelated alone)
    for r in rows:
        port = r["port_id"]
        channel = int(port.rsplit("-", 1)[-1])
        vals = (
            port,
            r["parent_node_id"],
            r["board_location"],
            channel,
            r["user_name"],
            "Searchlight Signal Head",
            "5V",
            (
                f"HART Digicon; MQTT {r['topic']}; "
                f"packed {r['packed']} (node {r['mqtt_node']} sig {r['signal_index']})"
            ),
        )
        if port in by_port:
            rr = by_port[port]
            for col, v in enumerate(vals, start=1):
                ws.cell(rr, col, v)
        else:
            ws.append(vals)
    # Annotate leftover C4-OU3 dwarf ports (not Digicon-converted) so they aren't confused
    for port in ("C4-OU3-1", "C4-OU3-2"):
        if port in by_port and port not in assigned:
            rr = by_port[port]
            note = ws.cell(rr, 8).value or ""
            if "Brick East Main West" not in str(note):
                ws.cell(
                    rr,
                    8,
                    (str(note) + " | reserved / not Digicon head-mast").strip(" |"),
                )
    out = DATA / "LCOS_Layout_Inventory_v48_signal_ports.xlsx"
    wb.save(out)
    wb.save(inv)  # update Downloads copy too
    print(f"updated inventory DNOU8 → {inv} and {out}")


def write_cats_virtual_3() -> None:
    """3-head appearance from Digicon triple ASPECTMAP + AAR SL-3 imagelinks."""
    # Exact Digicon SIGNALTEMPLATE triple ASPECTMAP (HART_Master / West_Yard2).
    amap = {
        "R281": "green|red|red",
        "R281B": "green|red|red",
        "R281C": "green|red|red",
        "C412": "green|red|red",
        "R285": "yellow|red|red",
        "R281D": "yellow|red|red",
        "R282": "yellow|yellow|red",
        "R284": "yellow|yellow|red",
        "ADV_NORM": "yellow|yellow|red",
        "ADV_LIM": "yellow|yellow|red",
        "C413": "yellow|yellow|red",
        "C414": "yellow|yellow|red",
        "R283": "red|green|red",
        "R283A": "red|green|red",
        "R283B": "red|green|red",
        "C417": "red|green|red",
        "ADV_MED": "red|green|red",
        "R286": "red|yellow|red",
        "R287": "red|red|green",
        "C422": "red|red|green",
        "C423": "red|red|green",
        "C424": "red|red|green",
        "ADV_SLO": "red|red|green",
        "R288": "red|red|yellow",
        "RES_NORM": "red|red|red",
        "RES_LIM": "red|red|red",
        "RES_MED": "red|red|red",
        "RES_SLO": "red|red|red",
        "R291": "red|red|red",
        "R292": "red|red|red",
    }
    # Prefer matching rule gif when present
    icon = {
        "R281": "rule-281.gif",
        "R281B": "rule-281B.gif",
        "R281C": "rule-281C.gif",
        "R281D": "rule-285.gif",
        "R282": "rule-282.gif",
        "R284": "rule-284.gif",
        "R285": "rule-285.gif",
        "R283": "rule-283.gif",
        "R283A": "rule-283A.gif",
        "R283B": "rule-283B.gif",
        "R286": "rule-286.gif",
        "R287": "rule-287.gif",
        "R288": "rule-288.gif",
        "R291": "rule-292.gif",
        "R292": "rule-292.gif",
    }
    base = "../../../resources/icons/smallschematics/aspects/AAR-1946/SL-3-high/"
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<?xml-stylesheet href="../../XSLT/appearancetable.xsl" type="text/xsl"?>',
        "<!-- Three-head cats-virtual; Digicon triple ASPECTMAP + SL-3 imagelinks. -->",
        '<appearancetable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '    xsi:noNamespaceSchemaLocation="http://jmri.org/xml/schema/appearancetable.xsd">',
        "  <aspecttable>CATS Virtual Signals</aspecttable>",
        "  <name>cats-virtual-3</name>",
        "  <reference>CATS Digicon triple-lamp PHYSIGNAL aspect keys</reference>",
        "  <description>Three searchlight heads driven by Digicon R/C/RES/ADV indication names</description>",
        "  <appearances>",
    ]
    for aspect, colors in amap.items():
        shows = "".join(f"<show>{c}</show>" for c in colors.split("|"))
        gif = icon.get(aspect, "rule-292.gif")
        lines.append(
            f"    <appearance><aspectname>{aspect}</aspectname>{shows}"
            f'<imagelink type="default">{base}{gif}</imagelink></appearance>'
        )
    stop = f"{base}rule-292.gif"
    lines += [
        "  </appearances>",
        "  <specificappearances>",
        "    <danger><aspect>R292</aspect></danger>",
        "    <held>",
        "      <aspect>R292</aspect>",
        f'      <imagelink type="default">{stop}</imagelink>',
        "    </held>",
        "    <dark>",
        "      <aspect>R292</aspect>",
        f'      <imagelink type="default">{stop}</imagelink>',
        "    </dark>",
        "    <permissive><aspect>R285</aspect></permissive>",
        "  </specificappearances>",
        "  <aspectMappings/>",
        "</appearancetable>",
        "",
    ]
    (CATS_MASTS / "appearance-cats-virtual-3.xml").write_text("\n".join(lines))
    # Ensure single-head file name element is cats-virtual (file stem match)
    single = CATS_MASTS / "appearance-cats-virtual.xml"
    t = single.read_text()
    t = re.sub(r"<name>Default</name>", "<name>cats-virtual</name>", t)
    single.write_text(t)
    # aspects.xml appearancefiles
    aspects = CATS_MASTS / "aspects.xml"
    at = aspects.read_text()
    if "appearance-cats-virtual-3.xml" not in at:
        at = at.replace(
            '    <appearancefile href="appearance-cats-virtual-2.xml" />\n  </appearancefiles>',
            '    <appearancefile href="appearance-cats-virtual-2.xml" />\n'
            '    <appearancefile href="appearance-cats-virtual-3.xml" />\n'
            "  </appearancefiles>",
        )
        aspects.write_text(at)
    print("wrote appearance-cats-virtual-3.xml; updated aspects + cats-virtual name")


def _heads_xml(rows: list[dict]) -> str:
    # Keep legacy IH410 if present elsewhere — we replace whole signalheads block content carefully
    parts = [
        '  <signalheads class="jmri.managers.configurexml.AbstractSignalHeadManagerXml">',
        '    <signalhead class="jmri.implementation.configurexml.VirtualSignalHeadXml">',
        "      <systemName>IH410</systemName>",
        "    </signalhead>",
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
        '    <mqttsignalmast class="jmri.jmrix.mqtt.configurexml.MqttSignalMastXml">',
        "      <systemName>IF$mqm:AAR-1946:SL-1-high-abs($464)</systemName>",
        "      <userName>Brick East Main West</userName>",
        '      <unlit allowed="no" />',
        "      <disabledAspects>",
        "        <disabledAspect>Restricting</disabledAspect>",
        "      </disabledAspects>",
        "    </mqttsignalmast>",
    ]
    seen = set()
    for r in rows:
        m = r["mast_user_name"]
        if m in seen:
            continue
        seen.add(m)
        sysname = mast_system_name(m, rows)
        parts.append(
            '    <signalmast class="jmri.implementation.configurexml.SignalHeadSignalMastXml">'
        )
        parts.append(f"      <systemName>{sysname}</systemName>")
        parts.append(f"      <userName>{m}</userName>")
        parts.append('      <unlit allowed="no" />')
        parts.append("    </signalmast>")
    parts.append("  </signalmasts>")
    return "\n".join(parts)


def patch_tables(rows: list[dict]) -> None:
    heads = _heads_xml(rows)
    masts = _masts_xml(rows)
    block = heads + "\n" + masts
    files = [
        ROOT / "tables/new_tables.xml",
        ROOT / "jmri/layouts/hart/output/tables.xml",
        ROOT / "jmri/layouts/hart/output/pi_tables.xml",
        ROOT / "jmri/layouts/hart/output/hart_prod.xml",
    ]
    # Match from <signalheads ...> through </signalmasts>
    pat = re.compile(
        r"  <signalheads class=\"jmri\.managers\.configurexml\.AbstractSignalHeadManagerXml\">.*?"
        r"  </signalmasts>",
        re.S,
    )
    for path in files:
        text = path.read_text()
        if not pat.search(text):
            print(f"SKIP (no signalheads/masts block): {path}", file=sys.stderr)
            continue
        # Also strip any Plane East LE icon if reintroduced
        text2 = re.sub(
            r"\n\s*<signalmasticon signalmast=\"Plane East East Main Ext\"[^/]*/>\s*",
            "\n",
            text,
        )
        text2, n = pat.subn(block, text2, count=1)
        path.write_text(text2)
        print(f"patched {path.relative_to(ROOT)} (masts block replaced, n={n})")


def write_publisher(rows: list[dict]) -> None:
    names = [r["system_name"] for r in rows]
    path = ROOT / "jmri/scripts/mqtt_signalhead_publisher.py"
    path.write_text(
        f'''# Publish Virtual Signal Head appearances to MQTT (JMRI → broker).
# HART Digicon lamps → LCOS packed IH### (node*100 + UID 32+index).
# Generated by cats/scripts/build_hart_signal_heads.py — see cats/data/signal_wiring.csv.
#
# Topic: track/signalhead/<systemName>   e.g. track/signalhead/IH432
# Payload: appearance name GREEN / YELLOW / RED / DARK / …
# Brick East Main West stays MQTT Signal Mast 464 (not listed here).
#
# Load after tables (profile Start Up). Requires JMRI MQTT connection.

import jmri
import java

class HartMqttSignalHeadPublisher(java.beans.PropertyChangeListener):
    def __init__(self, topic_prefix, head_names):
        self.topic_prefix = topic_prefix
        self.head_names = list(head_names)
        self.mqtt = None

    def start(self):
        memo = jmri.InstanceManager.getDefault(jmri.jmrix.mqtt.MqttSystemConnectionMemo)
        self.mqtt = memo.getMqttAdapter()
        for name in self.head_names:
            head = signals.getSignalHead(name)
            if head is None:
                print("HartMqttSignalHeadPublisher: missing head", name)
                continue
            head.addPropertyChangeListener(self)
            self._publish(head)
            print("HartMqttSignalHeadPublisher: listening", name)
        return

    def propertyChange(self, event):
        if event.propertyName == "Appearance":
            self._publish(event.source)
        return

    def _publish(self, head):
        topic = self.topic_prefix + head.getSystemName()
        data = head.getAppearanceName()
        print("HartMqttSignalHeadPublisher:", topic, data)
        self.mqtt.publish(topic, data)
        return

publisher = HartMqttSignalHeadPublisher(
    "track/signalhead/",
    {names!r},
)
publisher.start()
'''
    )
    print(f"wrote {path.relative_to(ROOT)} ({len(names)} heads)")


def main() -> int:
    rows = build_rows()
    write_csvs(rows)
    update_lcos_inventory(rows)
    write_cats_virtual_3()
    patch_tables(rows)
    write_publisher(rows)
    # summary by node
    by: dict[int, list] = {}
    for r in rows:
        by.setdefault(r["mqtt_node"], []).append(r)
    for node in sorted(by):
        print(
            f"node {node}: {len(by[node])} heads "
            f"packed {by[node][0]['packed']}…{by[node][-1]['packed']} "
            f"ports {by[node][0]['port_id']}…{by[node][-1]['port_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
