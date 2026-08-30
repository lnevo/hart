#!/usr/bin/env python3
"""Native-SML mimic QA: drive retained MQTT states, assert mast aspects via JMRI JSON.

Covers 100, 102, 110, 111, 114/115, K-1/K-2, A48 balloon, 117/117b.
Never publishes track/cmd/*. Captures retained baseline and restores it.

Live CATS ABS is HOLD_ONLY on the same JMRI masts (ADR-005 names: 120R, 114LB, …).
CATS-prefixed twin masts are gone, so this compares SML aspect vs MQTT head
appearance (what CATS ABS paints / LCOS sees). `held` is CATS ABS Hold.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

HOST = "minipc-e5h6x.local"
PUB = "/opt/local/bin/mosquitto_pub"
SUB = "/opt/local/bin/mosquitto_sub"
OUT = Path("/Users/lnevo/hart/cats/screenshots/mimic_qa")
PI = "pi"
SETTLE = 4.5

# switch -> (turnout MQTT addr, FB-normal sensor, FB-reverse sensor); None = DIRECT
TO = {
    "113": ("108", "167", "168"),
    "114": ("109", "169", "170"),
    "115": ("110", "171", "172"),
    "100": ("408", "470", "471"),
    "102": ("410", "474", "475"),
    "110": ("1211", "1273", "1274"),
    "111": ("1212", "1275", "1276"),
    "112": ("1213", "1277", "1278"),
    "117": ("1308", None, None),
}

# block name -> occupancy sensor MQTT addr
OCC = {
    "McKees Rocks": "100",
    "McKeesport": "101",
    "OS 114/K-2": "102",
    "OS 115/K-1": "103",
    "OS 113b": "104",
    "OS 113a": "105",
    "East Lead": "106",
    "West Main Ext": "107",
    "Main West": "200",
    "Main East": "202",
    "OS 100": "401",
    "OS 102": "404",
    "East Main Ext": "406",
    "OS 110": "1206",
    "OS 111a": "1203",
    "OS 111b": "1205",
    "OS 112": "1207",
}

TOUCHED_TOPICS = (
    [f"track/turnout/{a}" for a, _, _ in TO.values()]
    + [f"track/sensor/{fb}" for _, n, r in TO.values() for fb in (n, r) if fb]
    + [f"track/sensor/{a}" for a in OCC.values()]
)

STOPLIKE = {"Stop", "Unlit", "Dark", "Held", None, ""}


def pub(topic: str, payload: str) -> None:
    subprocess.check_call(
        [PUB, "-h", HOST, "-r", "-t", topic, "-m", payload],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def set_occ(block: str, state: str) -> None:
    pub(f"track/sensor/{OCC[block]}", state)


def set_to(sw: str, state: str) -> None:
    addr, n, r = TO[sw]
    thrown = state == "THROWN"
    if n and r:
        pub(f"track/sensor/{n}", "INACTIVE" if thrown else "ACTIVE")
        pub(f"track/sensor/{r}", "ACTIVE" if thrown else "INACTIVE")
    pub(f"track/turnout/{addr}", state)


def capture_baseline() -> dict:
    """Read current retained value of every topic we will touch."""
    base: dict[str, str] = {}
    for topic in TOUCHED_TOPICS:
        p = subprocess.run(
            [SUB, "-h", HOST, "-t", topic, "-C", "1", "-W", "2", "-v"],
            capture_output=True,
            text=True,
        )
        line = p.stdout.strip()
        if line:
            t, _, payload = line.partition(" ")
            base[t] = payload
    return base


LIVE_MASTS = {
    "101RA", "101RB", "100L", "102LA", "102LB",
    "117RA", "117RB", "117LA", "117LB",
    "111RA", "111RB", "111L", "110R", "112R", "112L",
    "113RA", "113RB", "120R", "120L", "114LA", "114LB", "115LA", "115LB",
}

# Mast userName -> head system names (signal_wiring.csv). MQTT appearance must
# match JMRI JSON for CATS ABS HOLD_ONLY paint.
MAST_HEADS = {
    "102LB": ("IH432", "IH433"),
    "102LA": ("IH434",),
    "101RA": ("IH436",),
    "101RB": ("IH437",),
    "100L": ("IH438", "IH439"),
    "117RA": ("IH1332", "IH1333"),
    "117LB": ("IH1334",),
    "117RB": ("IH1335", "IH1336"),
    "117LA": ("IH1337", "IH1338"),
    "111RA": ("IH1232", "IH1233"),
    "111L": ("IH1234", "IH1235"),
    "111RB": ("IH1236",),
    "112L": ("IH1237", "IH1238"),
    "110R": ("IH1239",),
    "112R": ("IH1240", "IH1241"),
    "115LB": ("IH132", "IH133"),
    "120R": ("IH134",),
    "113RA": ("IH135", "IH136"),
    "113RB": ("IH137", "IH138"),
    "114LB": ("IH139", "IH140"),
    "120L": ("IH141",),
    "115LA": ("IH142",),
    "114LA": ("IH143",),
}

STOP_HEAD = {"Red", "Dark", "Held", None, ""}


def _ssh_json(snippet: str) -> dict:
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", PI, "python3", "-"],
        input=snippet,
        capture_output=True,
        text=True,
        timeout=25,
    )
    if p.returncode != 0:
        raise SystemExit(p.stderr or p.stdout)
    line = [ln for ln in p.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def _mast_table_from_json(data) -> dict:
    out = {}
    for m in data:
        d = m["data"]
        un = d.get("userName") or d.get("name")
        out[un] = {"aspect": d.get("aspect"), "held": d.get("held")}
    return out


def jmri_snapshot() -> dict:
    """Prefer local JMRI JSON. CATS ABS on this Mac has no web server — use MQTT heads."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:12080/json/signalMast", timeout=2) as r:
            return _mast_table_from_json(json.load(r))
    except Exception:
        return snap_from_mqtt(mqtt_heads())


def mqtt_heads() -> dict:
    p = subprocess.run(
        [SUB, "-h", HOST, "-t", "track/signalhead/#", "-v", "-W", "2"],
        capture_output=True,
        text=True,
    )
    out = {}
    for line in p.stdout.splitlines():
        if " " not in line:
            continue
        topic, payload = line.split(" ", 1)
        sysn = topic.rsplit("/", 1)[-1]
        out[sysn] = payload.strip()
    return out


def snap_from_mqtt(heads: dict) -> dict:
    """Stop / Medium Clear / Clear / Approach from head colors (no JSON)."""
    out = {}
    for mast, ihs in MAST_HEADS.items():
        colors = [heads.get(ih) for ih in ihs]
        live = [c for c in colors if c not in STOP_HEAD]
        if not live:
            aspect = "Stop"
        elif "Green" in colors and "Red" in colors:
            aspect = "Medium Clear"
        elif "Green" in colors:
            aspect = "Clear"
        elif "Yellow" in colors:
            aspect = "Approach"
        else:
            aspect = live[0]
        out[mast] = {"aspect": aspect, "held": None}
    return out


def aspect_of(snap: dict, name: str):
    v = snap.get(name)
    if isinstance(v, dict):
        return v.get("aspect")
    return v


def render(snap: dict, heads_jmri: dict, heads_mqtt: dict) -> str:
    names = sorted(n for n in snap if n in LIVE_MASTS)
    lines = ["%-8s %-14s %-6s  MQTT heads" % ("mast", "SML", "held")]
    for name in names:
        rec = snap.get(name) or {}
        sml = rec.get("aspect") if isinstance(rec, dict) else rec
        held = rec.get("held") if isinstance(rec, dict) else ""
        bits = []
        for ih in MAST_HEADS.get(name, ()):
            mqtt = heads_mqtt.get(ih, "—")
            bits.append("%s=%s" % (ih, mqtt))
        lines.append("%-8s %-14s %-6s  %s" % (name, sml, held, " ".join(bits)))
    twins = [n for n in snap if n.startswith("CATS ")]
    if twins:
        lines.append("CATS-twin leftovers: " + ", ".join(sorted(twins)))
    return "\n".join(lines)


FAILURES: list[str] = []


def check(snap: dict, tag: str, expect: dict) -> None:
    for mast, want in expect.items():
        aspect = aspect_of(snap, mast)
        is_stop = aspect in STOPLIKE
        if want == "stop":
            ok = is_stop
        elif want == "nonstop":
            ok = not is_stop
        else:  # exact aspect name
            ok = aspect == want
        verdict = "PASS" if ok else "FAIL"
        line = f"[{verdict}] {tag}: {mast} = {aspect!r} (expected {want})"
        print(line)
        if not ok:
            FAILURES.append(line)


def check_mqtt_heads(snap: dict, heads_mqtt: dict, tag: str) -> None:
    """Stop-like SML must not leave a live Green/Yellow on any mast head."""
    for mast, ihs in MAST_HEADS.items():
        aspect = aspect_of(snap, mast)
        if aspect is None:
            continue
        colors = [heads_mqtt.get(ih) for ih in ihs]
        if aspect in STOPLIKE:
            ok = all(c in STOP_HEAD or c == "Red" for c in colors)
            if not ok:
                line = f"[FAIL] {tag}: {mast} SML={aspect!r} but MQTT {dict(zip(ihs, colors))}"
                print(line)
                FAILURES.append(line)
        elif aspect and aspect not in STOPLIKE:
            ok = any(c not in STOP_HEAD and c != "Red" for c in colors)
            if not ok:
                line = f"[FAIL] {tag}: {mast} SML={aspect!r} but MQTT all stop-like {dict(zip(ihs, colors))}"
                print(line)
                FAILURES.append(line)


NOTES: list[str] = []


def step(tag: str, desc: str, expect: dict | None = None) -> dict:
    time.sleep(SETTLE)
    snap = jmri_snapshot()
    heads_mqtt = mqtt_heads()
    blob = f"## {tag}\n{desc}\n{render(snap, {}, heads_mqtt)}\n"
    NOTES.append(blob)
    print(blob)
    if expect:
        check(snap, tag, expect)
    check_mqtt_heads(snap, heads_mqtt, tag)
    return snap


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("capturing retained baseline…", flush=True)
    baseline = capture_baseline()
    (OUT / "native_sml_qa_baseline.json").write_text(json.dumps(baseline, indent=1))
    print(f"captured {len(baseline)} retained topics")

    try:
        # ---- known rest state ----
        for sw, st in [
            ("113", "CLOSED"), ("114", "CLOSED"), ("115", "CLOSED"),
            ("110", "CLOSED"), ("111", "CLOSED"), ("112", "THROWN"),
            ("117", "CLOSED"), ("100", "CLOSED"), ("102", "CLOSED"),
        ]:
            set_to(sw, st)
        for blk in OCC:
            set_occ(blk, "INACTIVE")

        step(
            "qa00_rest",
            "All occ clear; 113/114/115/110/111/117/100/102 CLOSED, 112 THROWN (field rest).",
            {
                "120R": "nonstop",
                "120L": "nonstop",
                "115LA": "nonstop",      # dest 111L: Sw115+Sw111 closed
                "114LA": "nonstop",      # dest 112L: Sw113/114 closed
                "115LB": "stop",         # needs Sw115 thrown
                "114LB": "stop",         # needs Sw114 thrown
                "110R": "stop",          # needs Sw110 thrown
                "117LA": "nonstop",      # dest 102LB: Sw117 closed
            },
        )

        # ---- Princess 115 / K-1 / McKees Rocks leg ----
        set_to("115", "THROWN")
        step(
            "qa01_115_thrown",
            "115 THROWN: main runs via McKees Rocks balloon; K-1 cut off.",
            {
                "115LA": "stop",
                # diverging route (115 thrown) with dest 111L non-Stop: bottom head green
                "115LB": "Medium Clear",
                "120L": "nonstop",  # dest 115LB after Discover
                "113RA": "nonstop",  # dest 120L via 113C+115T
            },
        )

        set_occ("West Main Ext", "ACTIVE")
        step(
            "qa02_115T_wme_occ",
            "115 THROWN + West Main Ext occupied: Rocks-main path fouled.",
            {"115LB": "stop"},
        )
        set_occ("West Main Ext", "INACTIVE")
        set_to("115", "CLOSED")

        # ---- Princess 114 / K-2 / McKeesport leg + A48 balloon ----
        set_to("114", "THROWN")
        step(
            "qa03_114_thrown",
            "114 THROWN: main runs via McKeesport balloon; K-2 cut off.",
            {
                "114LB": "nonstop",
                "113RB": "nonstop",  # dest 120R via 113C+114T
            },
        )

        set_occ("McKeesport", "ACTIVE")
        step(
            "qa04_114T_mckeesport_occ",
            "114 THROWN + McKeesport balloon occupied (A48 boundary test).",
            {
                "120R": "stop",
                "113RB": "stop",
            },
        )
        set_occ("McKeesport", "INACTIVE")
        set_to("114", "CLOSED")

        # ---- K-2 occupancy path ----
        set_occ("East Lead", "ACTIVE")
        step(
            "qa05_east_lead_occ",
            "East Lead occupied: K-2's route to East Lead mast fouled; K-1 (via 111a) unaffected.",
            {
                "114LA": "stop",
                "115LA": "nonstop",
            },
        )
        set_occ("East Lead", "INACTIVE")

        # ---- OS 110 dwarf ('always red' regression) ----
        set_to("112", "CLOSED")
        set_to("110", "THROWN")
        step(
            "qa06_110T_112C",
            "110 THROWN + 112 CLOSED: ladder move OS110 -> East Lead -> 113a lined.",
            {"110R": "nonstop"},
        )
        set_to("110", "CLOSED")
        step(
            "qa07_110_closed",
            "110 CLOSED again: OS 110 dwarf back to Stop.",
            {"110R": "stop"},
        )
        set_to("112", "THROWN")

        # ---- 117 / 117b ----
        set_occ("East Main Ext", "ACTIVE")
        step(
            "qa08_eme_occ",
            "East Main Ext occupied: 117b's route to Plane EME fouled.",
            {"117LA": "stop"},
        )
        set_occ("East Main Ext", "INACTIVE")

        set_to("117", "THROWN")
        step(
            "qa09_117_thrown",
            "117 THROWN: T6 mast routes to Plane EME; 117b cut off.",
            {
                "117LB": "nonstop",
                "117LA": "stop",
            },
        )
        set_to("117", "CLOSED")

        # ---- Brick/Plane 100 & 102 ----
        set_to("100", "THROWN")
        step(
            "qa10_100_thrown",
            "100 THROWN + 102 CLOSED: Plane EME lined to EE West Main West.",
            {
                "102LB": "nonstop",
                "100L": "nonstop",   # dest 117RB via 100T+102C
                "111L": "Clear",
            },
        )
        set_occ("Main West", "ACTIVE")
        step(
            "qa11_100T_main_west_occ",
            "100 THROWN + Main West occupied: Plane EME route fouled.",
            {"102LB": "stop"},
        )
        set_occ("Main West", "INACTIVE")
        set_to("100", "CLOSED")

        step("qa12_back_to_rest", "Everything back at field rest.", {
            "115LA": "nonstop",
            "114LA": "nonstop",
            "117LA": "nonstop",
        })
    finally:
        print("restoring retained baseline…")
        for topic, payload in baseline.items():
            pub(topic, payload)
        time.sleep(SETTLE)
        step("qa99_restored", "Retained baseline restored.")

    (OUT / "native_sml_qa_notes.md").write_text("\n".join(NOTES))
    print("wrote", OUT / "native_sml_qa_notes.md")
    if FAILURES:
        print("\n%d FAILURE(S):" % len(FAILURES))
        for f in FAILURES:
            print(" ", f)
        raise SystemExit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
