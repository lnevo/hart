#!/usr/bin/env python3
"""Native-SML mimic QA: drive retained MQTT states, assert mast aspects via JMRI JSON.

Covers the known-bad list from the native-SML plan: 100, 102, 111, 114/115,
K-1/K-2, A48 balloon, OS 110, 117/117b. Never publishes track/cmd/*.
Captures the retained baseline of every topic it touches and restores it at the end.
"""
from __future__ import annotations

import json
import subprocess
import time
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


def jmri_snapshot() -> dict:
    remote = r"""
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:12080/json/signalMast", timeout=8) as r:
    data = json.load(r)
out = {}
for m in data:
    d = m["data"]
    un = d.get("userName") or d.get("name")
    out[un] = d.get("aspect")
print(json.dumps(out))
"""
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", PI, "python3", "-"],
        input=remote,
        capture_output=True,
        text=True,
        timeout=25,
    )
    if p.returncode != 0:
        raise SystemExit(p.stderr or p.stdout)
    line = [ln for ln in p.stdout.splitlines() if ln.startswith("{")][-1]
    return json.loads(line)


def render(snap: dict) -> str:
    names = sorted(n for n in snap if not n.startswith("CATS "))
    lines = ["%-42s %-14s %s" % ("mast", "SML", "CATS-twin")]
    for name in names:
        sml = snap.get(name)
        cats = snap.get("CATS " + name, "—")
        mark = "" if cats in ("—", sml) else "  twin-diff"
        lines.append("%-42s %-14s %-14s%s" % (name, sml, cats, mark))
    return "\n".join(lines)


FAILURES: list[str] = []


def check(snap: dict, tag: str, expect: dict) -> None:
    for mast, want in expect.items():
        aspect = snap.get(mast)
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


NOTES: list[str] = []


def step(tag: str, desc: str, expect: dict | None = None) -> dict:
    time.sleep(SETTLE)
    snap = jmri_snapshot()
    blob = f"## {tag}\n{desc}\n{render(snap)}\n"
    NOTES.append(blob)
    print(blob)
    if expect:
        check(snap, tag, expect)
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
                "Princess East McKeesport": "nonstop",
                "Princess East McKees Rocks": "nonstop",
                "Princess East K-1": "nonstop",      # dest 111a: Sw115+Sw111 closed
                "Princess East K-2": "nonstop",      # dest East Lead: Sw113/114 closed
                "Princess North McKees Rocks": "stop",  # needs Sw115 thrown
                "Princess South McKeesport": "stop",    # needs Sw114 thrown
                "East End South OS 110": "stop",        # needs Sw110 thrown
                "West Yard East OS 117b": "nonstop",    # dest Plane EME: Sw117 closed
            },
        )

        # ---- Princess 115 / K-1 / McKees Rocks leg ----
        set_to("115", "THROWN")
        step(
            "qa01_115_thrown",
            "115 THROWN: main runs via McKees Rocks balloon; K-1 cut off.",
            {
                "Princess East K-1": "stop",
                # diverging route (115 thrown) with dest 111a non-Stop: bottom head green
                "Princess North McKees Rocks": "Medium Clear",
                "Princess West OS 113b": "nonstop",  # dest McKeesport-mast via 113C+115T
            },
        )

        set_occ("West Main Ext", "ACTIVE")
        step(
            "qa02_115T_wme_occ",
            "115 THROWN + West Main Ext occupied: Rocks-main path fouled.",
            {"Princess North McKees Rocks": "stop"},
        )
        set_occ("West Main Ext", "INACTIVE")
        set_to("115", "CLOSED")

        # ---- Princess 114 / K-2 / McKeesport leg + A48 balloon ----
        set_to("114", "THROWN")
        step(
            "qa03_114_thrown",
            "114 THROWN: main runs via McKeesport balloon; K-2 cut off.",
            {
                "Princess South McKeesport": "nonstop",
                "Princess West OS 113a": "nonstop",  # dest McKees Rocks-mast via 113C+114T
            },
        )

        set_occ("McKeesport", "ACTIVE")
        step(
            "qa04_114T_mckeesport_occ",
            "114 THROWN + McKeesport balloon occupied (A48 boundary test).",
            {
                "Princess East McKeesport": "stop",
                "Princess West OS 113a": "stop",
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
                "Princess East K-2": "stop",
                "Princess East K-1": "nonstop",
            },
        )
        set_occ("East Lead", "INACTIVE")

        # ---- OS 110 dwarf ('always red' regression) ----
        set_to("112", "CLOSED")
        set_to("110", "THROWN")
        step(
            "qa06_110T_112C",
            "110 THROWN + 112 CLOSED: ladder move OS110 -> East Lead -> 113a lined.",
            {"East End South OS 110": "nonstop"},
        )
        set_to("110", "CLOSED")
        step(
            "qa07_110_closed",
            "110 CLOSED again: OS 110 dwarf back to Stop.",
            {"East End South OS 110": "stop"},
        )
        set_to("112", "THROWN")

        # ---- 117 / 117b ----
        set_occ("East Main Ext", "ACTIVE")
        step(
            "qa08_eme_occ",
            "East Main Ext occupied: 117b's route to Plane EME fouled.",
            {"West Yard East OS 117b": "stop"},
        )
        set_occ("East Main Ext", "INACTIVE")

        set_to("117", "THROWN")
        step(
            "qa09_117_thrown",
            "117 THROWN: T6 mast routes to Plane EME; 117b cut off.",
            {
                "West Yard East Yard T6": "nonstop",
                "West Yard East OS 117b": "stop",
            },
        )
        set_to("117", "CLOSED")

        # ---- Brick/Plane 100 & 102 ----
        set_to("100", "THROWN")
        step(
            "qa10_100_thrown",
            "100 THROWN + 102 CLOSED: Plane EME lined to EE West Main West.",
            {
                "Plane East East Main Ext": "nonstop",
                "Brick East Main West": "nonstop",   # dest WY West EME via 100T+102C
                # straight route behind a non-Stop Brick EMW: 3-aspect chaining gives Clear
                "East End East OS 111a": "Clear",
            },
        )
        set_occ("Main West", "ACTIVE")
        step(
            "qa11_100T_main_west_occ",
            "100 THROWN + Main West occupied: Plane EME route fouled.",
            {"Plane East East Main Ext": "stop"},
        )
        set_occ("Main West", "INACTIVE")
        set_to("100", "CLOSED")

        step("qa12_back_to_rest", "Everything back at field rest.", {
            "Princess East K-1": "nonstop",
            "Princess East K-2": "nonstop",
            "West Yard East OS 117b": "nonstop",
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
