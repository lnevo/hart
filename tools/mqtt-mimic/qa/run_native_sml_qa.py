#!/usr/bin/env python3
"""Native-SML mimic QA: drive retained MQTT states, assert mast aspects via JMRI JSON.

Covers 100, 102, 110, 111, 114/115, K-1/K-2, A48 balloon, 117/117b.
Never publishes track/cmd/*. Captures retained baseline and restores it.

Live CATS ABS is HOLD_ONLY on the same JMRI masts (ADR-005 names).
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
OUT = Path(__file__).resolve().parent
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
    "Mast 4RA", "Mast 4RB", "Mast 2L", "Mast 6LA", "Mast 6LB",
    "Mast 8RA", "Mast 8RB", "Mast 8LA", "Mast 8LB",
    "Mast 24RA", "Mast 24RB", "Mast 24L", "Mast 32R", "Mast 34R", "Mast 34L",
    "Mast 36RA", "Mast 36RB", "Mast 2036", "Mast 2035", "Mast 38LA", "Mast 38LB", "Mast 40LA", "Mast 40LB",
}

# Mast userName -> head system names (signal_wiring.csv). MQTT appearance must
# match JMRI JSON for CATS ABS HOLD_ONLY paint.
MAST_HEADS = {
    "Mast 6LB": ("IH432", "IH433"),
    "Mast 6LA": ("IH434",),
    "Mast 4RA": ("IH436",),
    "Mast 4RB": ("IH437",),
    "Mast 2L": ("IH438", "IH439"),
    "Mast 8RA": ("IH1332", "IH1333"),
    "Mast 8LB": ("IH1334",),
    "Mast 8RB": ("IH1335", "IH1336"),
    "Mast 8LA": ("IH1337", "IH1338"),
    "Mast 24RA": ("IH1232", "IH1233"),
    "Mast 24L": ("IH1234", "IH1235"),
    "Mast 24RB": ("IH1236",),
    "Mast 34L": ("IH1237", "IH1238"),
    "Mast 32R": ("IH1239",),
    "Mast 34R": ("IH1240", "IH1241"),
    "Mast 40LB": ("IH132", "IH133"),
    "Mast 2036": ("IH134",),
    "Mast 36RA": ("IH135", "IH136"),
    "Mast 36RB": ("IH137", "IH138"),
    "Mast 38LB": ("IH139", "IH140"),
    "Mast 2035": ("IH141",),
    "Mast 40LA": ("IH142",),
    "Mast 38LA": ("IH143",),
}

STOP_HEAD = {"Red", "Dark", "Held", None, ""}


def _mast_table_from_json(data) -> dict:
    out = {}
    for m in data:
        d = m["data"]
        un = d.get("userName") or d.get("name")
        out[un] = {"aspect": d.get("aspect"), "held": d.get("held")}
    return out


def jmri_snapshot() -> dict:
    """JMRI JSON from the Pi or this Mac; CATS alone has no web server, so fall back to MQTT heads."""
    for host in (HOST, "127.0.0.1"):
        try:
            with urllib.request.urlopen(f"http://{host}:12080/json/signalMast", timeout=2) as r:
                return _mast_table_from_json(json.load(r))
        except Exception:
            continue
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


def aspect_from_heads(colors: list) -> str:
    """Basic aspect from head colors, top head first (two-searchlight or one-low)."""
    top = colors[0] if colors else None
    bottom = colors[1] if len(colors) > 1 else None
    if len(colors) == 1:
        return {"Green": "Clear", "Yellow": "Approach"}.get(top, "Stop")
    if top == "Green":
        return "Clear"
    if top == "Yellow":
        return "Approach"
    if bottom == "Green":
        return "Diverging Clear"
    if bottom == "Yellow":
        return "Diverging Approach"
    return "Stop"


def snap_from_mqtt(heads: dict) -> dict:
    """Aspects from head colors when JMRI JSON is unavailable."""
    return {
        mast: {"aspect": aspect_from_heads([heads.get(ih) for ih in ihs]), "held": None}
        for mast, ihs in MAST_HEADS.items()
    }


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
                "Mast 2036": "nonstop",
                "Mast 2035": "nonstop",
                "Mast 40LA": "nonstop",      # dest Mast 24L: Sw115+Sw111 closed
                "Mast 38LA": "nonstop",      # dest Mast 34L: Sw113/114 closed
                "Mast 40LB": "stop",         # needs Sw115 thrown
                "Mast 38LB": "stop",         # needs Sw114 thrown
                "Mast 32R": "stop",          # needs Sw110 thrown
                "Mast 8LA": "nonstop",      # dest Mast 6LB: Sw117 closed
            },
        )

        # ---- Princess 115 / K-1 / McKees Rocks leg ----
        set_to("115", "THROWN")
        step(
            "qa01_115_thrown",
            "115 THROWN: main runs via McKees Rocks balloon; K-1 cut off.",
            {
                "Mast 40LA": "stop",
                # diverging route (115 thrown) with dest Mast 24L non-Stop: bottom head green
                "Mast 40LB": "Diverging Clear",
                "Mast 2035": "nonstop",  # dest Mast 40LB after Discover
                "Mast 36RA": "nonstop",  # dest Mast 2035 via 113C+115T
            },
        )

        set_occ("West Main Ext", "ACTIVE")
        step(
            "qa02_115T_wme_occ",
            "115 THROWN + West Main Ext occupied: Rocks-main path fouled.",
            {"Mast 40LB": "stop"},
        )
        set_occ("West Main Ext", "INACTIVE")
        set_to("115", "CLOSED")

        # ---- Princess 114 / K-2 / McKeesport leg + A48 balloon ----
        set_to("114", "THROWN")
        step(
            "qa03_114_thrown",
            "114 THROWN: main runs via McKeesport balloon; K-2 cut off.",
            {
                "Mast 38LB": "nonstop",
                "Mast 36RB": "nonstop",  # dest Mast 2036 via 113C+114T
            },
        )

        set_occ("McKeesport", "ACTIVE")
        step(
            "qa04_114T_mckeesport_occ",
            "114 THROWN + McKeesport balloon occupied (A48 boundary test).",
            {
                "Mast 2036": "stop",
                "Mast 36RB": "stop",
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
                "Mast 38LA": "stop",
                "Mast 40LA": "nonstop",
            },
        )
        set_occ("East Lead", "INACTIVE")

        # ---- OS 110 dwarf ('always red' regression) ----
        set_to("112", "CLOSED")
        set_to("110", "THROWN")
        step(
            "qa06_110T_112C",
            "110 THROWN + 112 CLOSED: ladder move OS110 -> East Lead -> 113a lined.",
            {"Mast 32R": "nonstop"},
        )
        set_to("110", "CLOSED")
        step(
            "qa07_110_closed",
            "110 CLOSED again: OS 110 dwarf back to Stop.",
            {"Mast 32R": "stop"},
        )
        set_to("112", "THROWN")

        # ---- 117 / 117b ----
        set_occ("East Main Ext", "ACTIVE")
        step(
            "qa08_eme_occ",
            "East Main Ext occupied: 117b's route to Plane EME fouled.",
            {"Mast 8LA": "stop"},
        )
        set_occ("East Main Ext", "INACTIVE")

        set_to("117", "THROWN")
        step(
            "qa09_117_thrown",
            "117 THROWN: T6 mast routes to Plane EME; 117b cut off.",
            {
                "Mast 8LB": "nonstop",
                "Mast 8LA": "stop",
            },
        )
        set_to("117", "CLOSED")

        # ---- Brick/Plane 100 & 102 ----
        set_to("100", "THROWN")
        step(
            "qa10_100_thrown",
            "100 THROWN + 102 CLOSED: Plane EME lined to EE West Main West.",
            {
                "Mast 6LB": "nonstop",
                "Mast 2L": "nonstop",   # dest Mast 8RB via 100T+102C
                "Mast 24L": "Clear",
            },
        )
        set_occ("Main West", "ACTIVE")
        step(
            "qa11_100T_main_west_occ",
            "100 THROWN + Main West occupied: Plane EME route fouled.",
            {"Mast 6LB": "stop"},
        )
        set_occ("Main West", "INACTIVE")
        set_to("100", "CLOSED")

        step("qa12_back_to_rest", "Everything back at field rest.", {
            "Mast 40LA": "nonstop",
            "Mast 38LA": "nonstop",
            "Mast 8LA": "nonstop",
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
