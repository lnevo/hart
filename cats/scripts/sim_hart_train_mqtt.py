#!/usr/bin/env python3
"""Simulate one train on HART via MQTT — contiguous Digicon + JMRI neighbors.

Broker / topics match JMRI profile M2 (empty channel):
  track/sensor/{addr}   ACTIVE | INACTIVE
  track/turnout/{addr}  CLOSED | THROWN

Routes walk Digicon SecEdge-adjacent blocks (one red segment at a time).
Each step is also checked against JMRI layoutblock adjacency from hart_prod
so you can relay the same move onto the Neville / JMRI panel.

Usage:
  cats/.venv/bin/python cats/scripts/sim_hart_train_mqtt.py
  cats/.venv/bin/python cats/scripts/sim_hart_train_mqtt.py --routes main,princess,return
  cats/.venv/bin/python cats/scripts/sim_hart_train_mqtt.py --list-routes
  cats/.venv/bin/python cats/scripts/sim_hart_train_mqtt.py --clear-only
"""

from __future__ import annotations

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "paho-mqtt required. Use: cats/.venv/bin/python cats/scripts/sim_hart_train_mqtt.py\n"
        f"(import error: {e})"
    ) from e

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "cats" / "panels" / "HART.xml"
HART_PROD = ROOT / "jmri" / "layouts" / "hart" / "output" / "hart_prod.xml"

DEFAULT_HOST = "minipc-e5h6x.local"
DEFAULT_PORT = 1883

# CATS TRAINREPORTER / JMRI MQTT reporter (track/reporter/{addr}).
# Payload "locoId text" → IdTag; CATS matches Train.TRANSPONDING to locoId.
TRAIN_LOCO_ID = "4501"
TRAIN_SYMBOL = "HL1"
TRAIN_REPORT = f"{TRAIN_LOCO_ID} {TRAIN_SYMBOL}"

TURNOUT_LABELS: dict[str, str] = {
    "408": "Sw 100 (Brick)",
    "409": "Sw 101 (Brick)",
    "410": "Sw 102 (Plane)",
    "308": "Sw 103 (South Yard)",
    "309": "Sw 104 (South Yard)",
    "310": "Sw 105 (South Yard)",
    "311": "Sw 106 (South Yard)",
    "1208": "Sw 107 (East End)",
    "1209": "Sw 108 (East End)",
    "1210": "Sw 109 (East End)",
    "1211": "Sw 110 (East End)",
    "1212": "Sw 111 (East End xover)",
    "1213": "Sw 112 (East End)",
    "108": "Sw 113 (Princess)",
    "109": "Sw 114 (Princess → port)",
    "110": "Sw 115 (Princess → Rocks)",
    "411": "Sw 116 (West Yard)",
    "1308": "Sw 117 (West Yard)",
    "1309": "Sw 118 (West Yard)",
    "1310": "Sw 119 (West Yard)",
}

BASE_TURNOUTS: dict[str, str] = {a: "CLOSED" for a in TURNOUT_LABELS}


@dataclass(frozen=True)
class Step:
    block: str
    digicon: str
    jmri: str
    note: str = ""
    deck_transfer: bool = False  # Chubb rows are not SecEdge-linked


@dataclass
class Route:
    key: str
    title: str
    summary: str
    turnouts: dict[str, str]
    steps: list[Step] = field(default_factory=list)


def _merge(base: dict[str, str], override: dict[str, str]) -> dict[str, str]:
    out = dict(base)
    out.update(override)
    return out


# Digicon spines after Armstrong primary remap (see jmri_to_cats_digicon.py).
# main = Armstrong spine MW→100→OS Main West Brick–Plane→102→EME→… (JMRI-adjacent).
# princess / south_yard / yard may need deck_transfer where Armstrong ≠ Neville.
ROUTES: dict[str, Route] = {
    "main": Route(
        key="main",
        title="Route 1 — OS Main West → OS East Lead (R1 contiguous)",
        summary="Digicon R1 spine + JMRI: MW→100→Block→102→EME→117→OS Main East→112→OS East Lead",
        turnouts=_merge(BASE_TURNOUTS, {}),
        steps=[
            Step("OS Main West", "R1 far left", "OS Main West (top spine west)", "Start"),
            Step("OS 1", "R1 · Brick", "Blue OS 1", ""),
            Step("OS Main West Brick–Plane", "R1 Brick→Plane", "OS Main West Brick–Plane", ""),
            Step("OS 5", "R1 · Plane", "Blue OS 5", ""),
            Step("OS East Main Ext", "R1 east of Plane", "OS East Main Ext", ""),
            Step(
                "OS 7b (OS Barn)",
                "R1 · OS Barn/117b",
                "Blue OS 7b (bottom C/D)",
                "OS Main East↔EME uses 117 bottom — not 117 top (M2S1302)",
            ),
            Step("OS Main East", "R1 mid-east", "OS Main East (bottom spine)", ""),
            Step("OS 33", "R1 · East End", "Blue OS 33", ""),
            Step("OS East Lead", "R1 far right", "OS East Lead", "End R1 spine — next deck is R3 for Princess"),
        ],
    ),
    "princess": Route(
        key="princess",
        title="Route 2 — Princess reverse via OS McKeesport (R3 contiguous)",
        summary="Deck transfer to R3, then Digicon f-spine: W Main Ext→113b→113a→114→OS McKeesport→reverse",
        turnouts=_merge(
            BASE_TURNOUTS,
            {"108": "CLOSED", "109": "THROWN", "110": "CLOSED"},
        ),
        steps=[
            Step(
                "OS East Lead",
                "R1 OS East Lead",
                "OS East Lead",
                "Still on R1; next step transfers to R3 (Chubb decks are separate)",
            ),
            Step(
                "OS West Main Ext",
                "R3 far left",
                "OS West Main Ext",
                "CTC deck change R1→R3",
                deck_transfer=True,
            ),
            Step("OS 35b", "R3 Princess", "Blue OS 35b · Sw 113", "JMRI: OS East Lead↔113b↔OS West Main Ext"),
            Step("OS 35a", "R3", "Blue OS 35a", ""),
            Step("OS 37", "R3 → port", "Blue OS 37 · Sw 114 THROWN", "Into OS McKeesport loop"),
            Step("OS McKeesport", "R3 OS McKeesport", "OS McKeesport", "Reverse here"),
            Step("OS 37", "R3 ← port", "Blue OS 37", "Backing out"),
            Step("OS 35a", "R3", "Blue OS 35a", ""),
            Step("OS 35b", "R3", "Blue OS 35b", ""),
            Step("OS West Main Ext", "R3 far left", "OS West Main Ext", ""),
            Step(
                "OS East Lead",
                "R1 OS East Lead",
                "OS East Lead",
                "Back on R1",
                deck_transfer=True,
            ),
        ],
    ),
    "return": Route(
        key="return",
        title="Route 3 — OS East Lead → OS Main West (R1 contiguous reverse)",
        summary="Westbound on the same Digicon/JMRI spine",
        turnouts=_merge(BASE_TURNOUTS, {}),
        steps=[
            Step("OS East Lead", "R1 far right", "OS East Lead", "Westbound"),
            Step("OS 33", "R1 · East End", "Blue OS 33", ""),
            Step("OS Main East", "R1 mid-east", "OS Main East", ""),
            Step(
                "OS 7b (OS Barn)",
                "R1 · OS Barn/117b",
                "Blue OS 7b (bottom C/D)",
                "",
            ),
            Step("OS East Main Ext", "R1", "OS East Main Ext", ""),
            Step("OS 5", "R1 · Plane", "Blue OS 5", ""),
            Step("OS Main West Brick–Plane", "R1", "OS Main West Brick–Plane", ""),
            Step("OS 1", "R1 · Brick", "Blue OS 1", ""),
            Step("OS Main West", "R1 far left", "OS Main West", "Home"),
        ],
    ),
    "south_yard": Route(
        key="south_yard",
        title="Route 4 — South Yard diverge (R1 lower track contiguous)",
        summary="From Plane into Digicon diverge OS103→108 (yard ladder cells under R1)",
        turnouts=_merge(
            BASE_TURNOUTS,
            {
                "308": "THROWN",
                "309": "THROWN",
                "310": "THROWN",
                "311": "THROWN",
            },
        ),
        steps=[
            Step("OS Main West", "R1 far left", "OS Main West", "Restart for South Yard"),
            Step("OS 1", "R1", "Blue OS 1", ""),
            Step("OS Main West Brick–Plane", "R1", "OS Main West Brick–Plane", ""),
            Step("OS 5", "R1 · Plane", "Blue OS 5", "Diverge (a4→a10/a16)"),
            Step("OS 15", "R1 diverge", "Blue OS 15 · Sw 103 THROWN", ""),
            Step("OS 17", "R1 diverge", "Blue OS 17", "Side cell; back via 103"),
            Step("OS 15", "R1 diverge", "Blue OS 15", "Rejoin diverge spine"),
            Step("OS 19", "R1 diverge", "Blue OS 19", ""),
            Step("OS 21", "R1 diverge", "Blue OS 21", ""),
            Step("OS 25", "R1 diverge", "Blue OS 25", ""),
            Step("OS 27", "R1 diverge", "Blue OS 27", "End Digicon diverge chain"),
        ],
    ),
    "yard": Route(
        key="yard",
        title="Route 5 — West Yard body (R2 contiguous)",
        summary="Digicon R2 path d1→d3→d10…d15 (leads branch, then yard tracks → 111a)",
        turnouts=_merge(
            BASE_TURNOUTS,
            {
                "409": "THROWN",
                "411": "THROWN",
                "1308": "THROWN",
                "1309": "THROWN",
                "1310": "THROWN",
            },
        ),
        steps=[
            Step(
                "OS 1",
                "R1 Brick",
                "Blue OS 1",
                "Approach; next step transfers to R2 yard deck",
            ),
            Step(
                "OS 3",
                "R2 far left",
                "Blue OS 3 · Sw 101",
                "CTC deck change R1→R2",
                deck_transfer=True,
            ),
            Step("OS 13", "R2 West Yard", "Blue OS 13", ""),
            # Digicon: d3 (118) junctions to d4 leads spur and d10 yard tracks
            Step("OS 11", "R2 junction", "Blue OS 11", "Junction → leads or tracks"),
            Step("OS 9", "R2 leads spur", "Blue OS 9", "Leads spur"),
            Step("OS 11", "R2 junction", "Blue OS 11", "Back to junction"),
            Step("OS S-R", "R2 Tracks", "OS S-R", "Into yard body (d10)"),
            Step("OS S-1", "R2 Tracks", "OS S-1", ""),
            Step("OS S-2", "R2 Tracks", "OS S-2", ""),
            Step("OS S-3", "R2 Tracks", "OS S-3", ""),
            Step("OS S-4", "R2 Tracks", "OS S-4", ""),
            Step("OS 23a", "R2 east", "Blue OS 23a", "East end of yard deck"),
        ],
    ),
    # Neville-style: top spine via OS West Main Ext / Princess, home via OS Main East·117·Plane·Brick
    "neville": Route(
        key="neville",
        title="Route Neville — OS Main West → W Main Ext → Princess → OS East Lead → OS Main East → 117 → Plane → Brick",
        summary="JMRI-true top path around Princess, then bottom home through 117b/Plane/Brick (OS Barn = 117 bottom)",
        turnouts=_merge(
            BASE_TURNOUTS,
            {"108": "CLOSED", "109": "THROWN", "110": "CLOSED"},
        ),
        steps=[
            Step("OS Main West", "R1 far left", "OS Main West (top spine west)", "Start — Neville west"),
            Step(
                "OS 23a",
                "R2 east (Digicon) / top main east (JMRI)",
                "Blue OS 23a · East End",
                "JMRI top spine east; Digicon parks 111a on R2",
                deck_transfer=True,
            ),
            Step(
                "OS West Main Ext",
                "R3 far left",
                "OS West Main Ext (toward Princess)",
                "Onto Princess approach",
                deck_transfer=True,
            ),
            Step("OS 35b", "R3 Princess", "Blue OS 35b · Sw 113", "Around Princess"),
            Step("OS 35a", "R3", "Blue OS 35a", ""),
            Step("OS 37", "R3 → port", "Blue OS 37 · Sw 114 THROWN", "OS McKeesport leg"),
            Step("OS McKeesport", "R3 OS McKeesport", "OS McKeesport", "Reverse in the loop"),
            Step("OS 37", "R3 ← port", "Blue OS 37", "Backing out"),
            Step("OS 35a", "R3", "Blue OS 35a", ""),
            Step("OS 35b", "R3", "Blue OS 35b", ""),
            Step(
                "OS East Lead",
                "R1 far right",
                "OS East Lead",
                "Out of Princess onto OS East Lead",
                deck_transfer=True,
            ),
            Step("OS 33", "R1 · East End", "Blue OS 33", "Westbound toward OS Main East"),
            Step("OS Main East", "R1 mid-east", "OS Main East (bottom spine)", ""),
            Step(
                "OS 7b (OS Barn)",
                "R1 · OS Barn/117b",
                "Blue OS 7b (bottom C/D) · OS Barn",
                "OS Main East↔EME = 117 bottom (M2S1303), not top 1302",
            ),
            Step("OS East Main Ext", "R1", "OS East Main Ext", ""),
            Step("OS 5", "R1 · Plane", "Blue OS 5", "Through Plane"),
            Step("OS Main West Brick–Plane", "R1 Brick↔Plane", "OS Main West Brick–Plane", ""),
            Step("OS 1", "R1 · Brick", "Blue OS 1", "Through Brick"),
            Step("OS Main West", "R1 far left", "OS Main West", "Home"),
        ],
    ),
}

DEFAULT_ROUTE_ORDER = ["neville", "main", "princess", "return", "south_yard", "yard", "return"]


def load_block_sensors(panel: Path) -> dict[str, str]:
    root = ET.parse(panel).getroot()
    out: dict[str, str] = {}
    for b in root.iter("BLOCK"):
        name = b.get("NAME")
        oc = b.find("OCCUPIEDSPEC")
        if not name or oc is None:
            continue
        ios = oc.find("IOSPEC")
        if ios is None or not ios.get("DECADDR"):
            continue
        out[name] = ios.get("DECADDR")
    return out


def load_digicon_adjacency(panel: Path) -> dict[str, set[str]]:
    """Named-block adjacency via Digicon SEC_EDGE grid links."""
    root = ET.parse(panel).getroot()
    cells: dict[tuple[int, int], dict] = {}
    for sec in root.iter("SECTION"):
        x, y = int(sec.get("X")), int(sec.get("Y"))
        edges: dict[str, set[str]] = {}
        for edge in sec.findall("SEC_EDGE"):
            e = edge.get("EDGE") or ""
            names = {b.get("NAME") for b in edge.findall("BLOCK") if b.get("NAME")}
            if e:
                edges[e] = names
        cells[(x, y)] = edges

    delta = {
        "LEFT": (-1, 0, "RIGHT"),
        "RIGHT": (1, 0, "LEFT"),
        "TOP": (0, -1, "BOTTOM"),
        "BOTTOM": (0, 1, "TOP"),
    }
    name_cells: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for (x, y), edges in cells.items():
        for names in edges.values():
            for n in names:
                name_cells[n].add((x, y))

    def block_at(x: int, y: int) -> set[str]:
        names: set[str] = set()
        for ns in cells.get((x, y), {}).values():
            names |= ns
        return names

    def neighbors(x: int, y: int) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for e, ed_names in cells.get((x, y), {}).items():
            if e not in delta:
                continue
            dx, dy, opp = delta[e]
            nx, ny = x + dx, y + dy
            if opp in cells.get((nx, ny), {}):
                out.append((nx, ny))
        return out

    adj: dict[str, set[str]] = defaultdict(set)
    for n, locs in name_cells.items():
        for sx, sy in locs:
            q = deque([(sx, sy)])
            seen = {(sx, sy)}
            while q:
                x, y = q.popleft()
                here = block_at(x, y) - {n}
                for o in here:
                    adj[n].add(o)
                    adj[o].add(n)
                for nx, ny in neighbors(x, y):
                    if (nx, ny) in seen:
                        continue
                    seen.add((nx, ny))
                    other = block_at(nx, ny) - {n}
                    if other:
                        for o in other:
                            adj[n].add(o)
                            adj[o].add(n)
                        continue
                    q.append((nx, ny))
    return adj


def load_jmri_adjacency(hart_prod: Path) -> dict[str, set[str]]:
    """Block adjacency from Layout Editor, including xover C/D legs.

    TO117: A/B = OS 7 (top, M2S1302); C/D = OS 7b (bottom, M2S1303).
    OS Main East / OS East Main Ext attach on C/D — not the top OS.
    """
    root = ET.parse(hart_prod).getroot()

    # Alias turnout blockcname "Switch 117b" → block userName "OS 7b (OS Barn)"
    aliases: dict[str, str] = {}
    for b in root.iter("block"):
        un = b.findtext("userName") or ""
        if un.startswith("OS ") and "(" in un:
            # "OS 7b (OS Barn)" also answers to "Switch 117b"
            num = un.split()[1] if len(un.split()) > 1 else ""
            if num:
                aliases[f"Switch {num}"] = un
                aliases[un] = un
        if un:
            aliases[un] = un

    def canon(name: str) -> str:
        return aliases.get(name, name)

    turnouts = {t.get("ident"): t for t in root.iter("layoutturnout") if t.get("ident")}

    def turnout_leg_block(t: ET.Element, type_name: str) -> str:
        """Map TURNOUT_A/B/C/D to the block that owns that xover/turnout leg."""
        leg = (type_name or "")[-1:]  # A/B/C/D
        if leg in ("A", "B"):
            raw = t.get("blockname") or ""
        elif leg == "C":
            raw = t.get("blockcname") or t.get("blockc") or t.get("blockname") or ""
        elif leg == "D":
            raw = t.get("blockdname") or t.get("blockd") or t.get("blockname") or ""
        else:
            raw = t.get("blockname") or ""
        return canon(raw)

    adj: dict[str, set[str]] = defaultdict(set)

    def add(a: str, b: str) -> None:
        a, b = canon(a), canon(b)
        if a and b and a != b:
            adj[a].add(b)
            adj[b].add(a)

    for ts in root.iter("tracksegment"):
        bn = canon(ts.get("blockname") or "")
        # JMRI LE XML uses connect1name/connect2name (not connect1/connect2).
        for c, ty in (
            (ts.get("connect1name") or ts.get("connect1"), ts.get("type1")),
            (ts.get("connect2name") or ts.get("connect2"), ts.get("type2")),
        ):
            if not c:
                continue
            if c in turnouts and ty and ty.startswith("TURNOUT_"):
                add(bn, turnout_leg_block(turnouts[c], ty))
            elif c in turnouts:
                add(bn, canon(turnouts[c].get("blockname") or ""))

    pp: dict[str, set[str]] = defaultdict(set)
    for ts in root.iter("tracksegment"):
        bn = canon(ts.get("blockname") or "")
        for c, ty in (
            (ts.get("connect1name") or ts.get("connect1"), ts.get("type1")),
            (ts.get("connect2name") or ts.get("connect2"), ts.get("type2")),
        ):
            if c and ty == "POS_POINT":
                pp[c].add(bn)
    for bset in pp.values():
        bs = list(bset)
        for i, a in enumerate(bs):
            for b in bs[i + 1 :]:
                add(a, b)
    return adj


def validate_route(
    route: Route,
    digicon_adj: dict[str, set[str]],
    jmri_adj: dict[str, set[str]],
) -> list[str]:
    warnings: list[str] = []
    prev: str | None = None
    for step in route.steps:
        if prev is None:
            prev = step.block
            continue
        d_ok = step.block in digicon_adj.get(prev, set()) or step.block == prev
        j_ok = step.block in jmri_adj.get(prev, set()) or step.block == prev
        if step.deck_transfer:
            if not j_ok and step.block != prev:
                warnings.append(
                    f"{route.key}: deck transfer {prev} → {step.block} not JMRI-adjacent"
                )
        elif not d_ok:
            warnings.append(
                f"{route.key}: Digicon BREAK {prev} → {step.block} "
                f"(neighbors={sorted(digicon_adj.get(prev, []))})"
            )
        elif not j_ok:
            warnings.append(
                f"{route.key}: Digicon OK but JMRI gap {prev} → {step.block} "
                f"(jmri neighbors={sorted(jmri_adj.get(prev, []))})"
            )
        prev = step.block
    return warnings


def connect(host: str, port: int) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"hart-train-sim-{int(time.time())}",
    )
    client.connect(host, port, keepalive=60)
    client.loop_start()
    time.sleep(0.2)
    return client


def pub(client: mqtt.Client, topic: str, payload: str, *, retain: bool) -> None:
    client.publish(topic, payload, qos=1, retain=retain)


def set_sensor(client: mqtt.Client, addr: str, active: bool) -> None:
    pub(client, f"track/sensor/{addr}", "ACTIVE" if active else "INACTIVE", retain=True)


def set_reporter(client: mqtt.Client, addr: str, content: str | None) -> None:
    """JMRI MQTT reporter: non-empty = IdTag report; empty clears current report."""
    pub(client, f"track/reporter/{addr}", content if content else "", retain=True)


def set_turnout(client: mqtt.Client, addr: str, state: str) -> None:
    pub(client, f"track/turnout/{addr}", state, retain=True)


def clear_all(client: mqtt.Client, sensors: dict[str, str]) -> None:
    for addr in sorted(set(sensors.values()), key=lambda a: int(a)):
        set_sensor(client, addr, False)
        set_reporter(client, addr, None)
    time.sleep(0.25)


def describe_turnout_delta(
    previous: dict[str, str] | None, desired: dict[str, str]
) -> list[str]:
    lines: list[str] = []
    prev = previous or {}
    for addr, state in sorted(desired.items(), key=lambda kv: int(kv[0])):
        if prev.get(addr) == state:
            continue
        label = TURNOUT_LABELS.get(addr, f"M2T{addr}")
        lines.append(f"  {label}: {state}")
    return lines


def align_route(
    client: mqtt.Client,
    turnouts: dict[str, str],
    *,
    previous: dict[str, str] | None,
) -> dict[str, str]:
    delta = describe_turnout_delta(previous, turnouts)
    if delta:
        print("\n── Turnout lineup (watch JMRI points) ──", flush=True)
        for line in delta:
            print(line, flush=True)
    for addr, state in turnouts.items():
        set_turnout(client, addr, state)
    time.sleep(0.4)
    return dict(turnouts)


def run_route(
    client: mqtt.Client,
    sensors: dict[str, str],
    route: Route,
    *,
    delay: float,
    occupied: set[str],
    digicon_adj: dict[str, set[str]],
    jmri_adj: dict[str, set[str]],
    use_reporter: bool = True,
) -> set[str]:
    print("\n" + "=" * 72, flush=True)
    print(route.title, flush=True)
    print(route.summary, flush=True)
    if use_reporter:
        print(
            f"Train content: {TRAIN_REPORT}  (MQTT track/reporter/{{addr}}; "
            "CATS: Appearance → Train Tracker ON)",
            flush=True,
        )
    print("=" * 72, flush=True)

    prev: str | None = None
    for i, step in enumerate(route.steps, 1):
        addr = sensors.get(step.block)
        if not addr:
            print(f"\n[{i}/{len(route.steps)}] SKIP unknown/unwired: {step.block}", flush=True)
            prev = step.block
            continue

        for a in sorted(occupied):
            if a != addr:
                set_sensor(client, a, False)
                if use_reporter:
                    set_reporter(client, a, None)
        occupied = {addr}
        set_sensor(client, addr, True)
        if use_reporter:
            set_reporter(client, addr, TRAIN_REPORT)

        link = ""
        if prev:
            d_ok = step.block in digicon_adj.get(prev, set()) or step.block == prev
            j_ok = step.block in jmri_adj.get(prev, set()) or step.block == prev
            if step.deck_transfer:
                link = "link=DECK TRANSFER (Chubb rows)"
            elif d_ok and j_ok:
                link = "link=Digicon+JMRI OK"
            elif d_ok:
                link = "link=Digicon OK · JMRI gap"
            else:
                link = "link=BREAK"

        print(f"\n[{i}/{len(route.steps)}] {step.block}  (MS{addr} ACTIVE)  {link}", flush=True)
        if use_reporter:
            print(f"  Content:  M2R{addr} ← {TRAIN_REPORT}", flush=True)
        print(f"  Digicon:  {step.digicon}", flush=True)
        print(f"  JMRI:     {step.jmri}", flush=True)
        if step.note:
            print(f"  Note:     {step.note}", flush=True)
        prev = step.block
        time.sleep(delay)

    return occupied


def list_routes() -> None:
    print("Available routes:\n")
    seen: set[str] = set()
    for key in DEFAULT_ROUTE_ORDER + list(ROUTES):
        if key in ROUTES and key not in seen:
            seen.add(key)
            r = ROUTES[key]
            print(f"  {key:12}  {r.title}")
            print(f"  {'':12}  {r.summary}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--panel", type=Path, default=PANEL)
    ap.add_argument("--hart-prod", type=Path, default=HART_PROD)
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument(
        "--routes",
        default=",".join(dict.fromkeys(DEFAULT_ROUTE_ORDER)),
        help="comma-separated route keys",
    )
    ap.add_argument("--list-routes", action="store_true")
    ap.add_argument("--clear-only", action="store_true")
    ap.add_argument("--no-turnouts", action="store_true")
    ap.add_argument(
        "--no-reporter",
        action="store_true",
        help="do not publish track/reporter content (train label / block value)",
    )
    ap.add_argument("--strict", action="store_true", help="abort on Digicon adjacency breaks")
    args = ap.parse_args()

    if args.list_routes:
        list_routes()
        return 0

    sensors = load_block_sensors(args.panel)
    digicon_adj = load_digicon_adjacency(args.panel)
    jmri_adj = load_jmri_adjacency(args.hart_prod) if args.hart_prod.is_file() else {}

    print(
        f"panel={args.panel}  sensors={len(sensors)}  "
        f"digicon_nodes={len(digicon_adj)}  jmri_nodes={len(jmri_adj)}  "
        f"broker={args.host}:{args.port}",
        flush=True,
    )
    print(
        "Mode: ONE block lit. Steps must be Digicon-adjacent "
        "(deck_transfer allowed between Chubb rows).",
        flush=True,
    )

    # Duplicates = christmas tree
    from collections import Counter

    c = Counter(sensors.values())
    dups = [a for a, n in c.items() if n > 1]
    if dups:
        print(f"WARNING: duplicate sensor bindings (multi-cell): {dups}", flush=True)

    route_keys = [k.strip() for k in args.routes.split(",") if k.strip()]
    for key in route_keys:
        if key not in ROUTES:
            raise SystemExit(f"unknown route {key!r}; use --list-routes")

    all_warn: list[str] = []
    for key in route_keys:
        all_warn.extend(validate_route(ROUTES[key], digicon_adj, jmri_adj))
    if all_warn:
        print("\nAdjacency check:", flush=True)
        for w in all_warn:
            print(f"  ! {w}", flush=True)
        if args.strict and any("BREAK" in w for w in all_warn):
            raise SystemExit("strict: Digicon adjacency breaks present")

    client = connect(args.host, args.port)
    occupied: set[str] = set()
    previous_turnouts: dict[str, str] | None = None
    try:
        print("clearing occupancy", flush=True)
        clear_all(client, sensors)
        if args.clear_only:
            return 0

        print(
            f"\nGuided tour: {len(route_keys)} route(s), delay={args.delay}s\n",
            flush=True,
        )
        for key in route_keys:
            route = ROUTES[key]
            if not args.no_turnouts:
                previous_turnouts = align_route(
                    client, route.turnouts, previous=previous_turnouts
                )
            occupied = run_route(
                client,
                sensors,
                route,
                delay=args.delay,
                occupied=occupied,
                digicon_adj=digicon_adj,
                jmri_adj=jmri_adj,
                use_reporter=not args.no_reporter,
            )

        print("\n── Tour complete — clearing occupancy ──", flush=True)
        clear_all(client, sensors)
    except KeyboardInterrupt:
        print("\ninterrupted — clearing", flush=True)
        clear_all(client, sensors)
    finally:
        client.loop_stop()
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
