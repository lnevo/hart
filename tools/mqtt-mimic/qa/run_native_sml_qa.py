#!/usr/bin/env python3
"""Native-SML mimic QA: drive retained MQTT states, assert mast aspects via JMRI JSON.

Covers the masts in LIVE_MASTS. Writes native_sml_qa_notes.md and the baseline here (gitignored run output).
Never publishes track/cmd/*. Captures retained baseline and restores it.

Live CATS ABS is HOLD_ONLY on the same JMRI masts (ADR-005 names).
CATS-prefixed twin masts are gone, so this compares SML aspect vs MQTT head
appearance (what CATS ABS paints / LCOS sees). `held` is CATS ABS Hold.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

OUT = Path(__file__).resolve().parent
# where the mosquitto clients are looked for: PATH, then MacPorts' bin folder (the Mac's install)
CLIENT_DIRS = (*os.environ.get("PATH", "").split(os.pathsep), "/opt/local/bin")
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import level_masts, paths, railroad, tables as tables_mod  # noqa: E402
from hartlib.hosts import jmri_json_url, mqtt_broker  # noqa: E402

ROOT = paths.REPO_ROOT
sys.path.insert(0, str(ROOT / "tools" / "audit"))
from check_wiring_crosswalk import read_tables  # noqa: E402

HOST = mqtt_broker()
JMRI_JSON = jmri_json_url()
LOCAL_JMRI_JSON = "http://127.0.0.1:12080/json"

TABLES = paths.TABLES_XML
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
    "K-1": "100",
    "K-2": "101",
    "OS 114/McKeesport": "102",
    "OS 115/McKees Rocks": "103",
    "OS 113b": "104",
    "OS 113a": "105",
    "East Lead": "106",
    "West Ext": "107",
    "Main West": "200",
    "Main East": "202",
    "OS 100": "401",
    "OS 102": "404",
    "East Ext": "406",
    "OS 110": "1206",
    "OS 111a": "1203",
    "OS 111b": "1205",
    "OS 112": "1207",
}

class QAError(Exception):
    """The QA cannot start: a mosquitto client is missing or tables.xml has a head mast it cannot read."""


def client(name: str) -> str:
    """The path of a mosquitto client (mosquitto_pub, mosquitto_sub); QAError naming the folders searched."""
    found = shutil.which(name, path=os.pathsep.join(CLIENT_DIRS))
    if found is None:
        raise QAError(f"{name} is not in PATH or /opt/local/bin; install the mosquitto clients")
    return found


TOUCHED_TOPICS = (
    [f"track/turnout/{a}" for a, _, _ in TO.values()]
    + [f"track/sensor/{fb}" for _, n, r in TO.values() for fb in (n, r) if fb]
    + [f"track/sensor/{a}" for a in OCC.values()]
)

STOPLIKE = {"Stop", "Unlit", "Dark", "Held", None, ""}


def pub(topic: str, payload: str) -> None:
    subprocess.check_call(
        [client("mosquitto_pub"), "-h", HOST, "-r", "-t", topic, "-m", payload],
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
            [client("mosquitto_sub"), "-h", HOST, "-t", topic, "-C", "1", "-W", "2", "-v"],
            capture_output=True,
            text=True,
        )
        line = p.stdout.strip()
        if line:
            t, _, payload = line.partition(" ")
            base[t] = payload
    return base


def load_live_masts(path: Path = level_masts.PATH) -> set[str]:
    """The live level's visible masts (head masts, IF$shsm): masts.csv's staging rows (hartlib.railroad
    STAGING_LEVEL, the level the QA runs on); the hidden virtual masts are left out."""
    live = (int(railroad.STAGING_LEVEL),)
    return {r["mast"] for r in level_masts.read(path, levels=live) if r["system_name"].startswith("IF$shsm:")}


LIVE_MASTS = load_live_masts()


def load_mast_heads(tables: Path | None = None) -> dict[str, tuple[str, ...]]:
    """Mast userName -> head system names, from the IF$shsm mast system names in tables.xml. The main and upper
    levels' masts on virtual heads (hartlib.level_masts) publish nothing until they are wired, so they are left out."""
    root = tables_mod.read(tables or TABLES)
    _comments, masts, bad = read_tables(root)
    if bad:
        raise QAError("tables.xml head masts the QA cannot read: " + "; ".join(bad))
    return {mast: tuple(heads) for mast, heads in masts.items()
            if not all(level_masts.is_level_head(h) for h in heads)}


# Mast userName -> head system names. MQTT appearance must match JMRI JSON for
# CATS ABS HOLD_ONLY paint. Mast 6LB reads ("IH432",), its one wired head (ADR-024).
MAST_HEADS = load_mast_heads()


STOP_HEAD = {"Red", "Dark", "Held", None, ""}


MastState = dict[str, object]        # {"aspect": str | None, "held": bool | None}


def _mast_table_from_json(data: Sequence[Mapping[str, Mapping[str, object]]]) -> dict[str, MastState]:
    out = {}
    for m in data:
        d = m["data"]
        un = d.get("userName") or d.get("name")
        out[un] = {"aspect": d.get("aspect"), "held": d.get("held")}
    return out


def jmri_snapshot() -> dict[str, MastState]:
    """JMRI JSON from the Pi or this Mac. CATS alone has no web server, so with neither answering the aspects come
    from the MQTT heads; each server that did not answer is named on stderr."""
    for base in dict.fromkeys((JMRI_JSON, LOCAL_JMRI_JSON)):
        try:
            with urllib.request.urlopen(f"{base}/signalMast", timeout=2) as r:
                return _mast_table_from_json(json.load(r))
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as err:
            print(f"JMRI JSON at {base}: {err}", file=sys.stderr)
    print("no JMRI JSON: the aspects come from the MQTT heads", file=sys.stderr)
    return snap_from_mqtt(mqtt_heads())


def mqtt_heads() -> dict[str, str]:
    p = subprocess.run(
        [client("mosquitto_sub"), "-h", HOST, "-t", "track/signalhead/#", "-v", "-W", "2"],
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


def aspect_from_heads(colors: Sequence[str | None]) -> str:
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


def snap_from_mqtt(heads: Mapping[str, str]) -> dict[str, MastState]:
    """Aspects from head colors when JMRI JSON is unavailable."""
    return {
        mast: {"aspect": aspect_from_heads([heads.get(ih) for ih in ihs]), "held": None}
        for mast, ihs in MAST_HEADS.items()
    }


def aspect_of(snap: Mapping[str, object], name: str) -> object:
    v = snap.get(name)
    if isinstance(v, dict):
        return v.get("aspect")
    return v


def render(snap: Mapping[str, object], heads_mqtt: Mapping[str, str]) -> str:
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


Want = str      # "stop", "nonstop", or an exact aspect name


@dataclass
class Run:
    """What one QA run collects: the notes file's sections and the failed checks."""
    notes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def fail(self, line: str) -> None:
        print(line)
        self.failures.append(line)


def check(run: Run, snap: Mapping[str, object], tag: str, expect: Mapping[str, Want]) -> None:
    for mast, want in expect.items():
        aspect = aspect_of(snap, mast)
        is_stop = aspect in STOPLIKE
        if want == "stop":
            ok = is_stop
        elif want == "nonstop":
            ok = not is_stop
        else:  # exact aspect name
            ok = aspect == want
        line = f"[{'PASS' if ok else 'FAIL'}] {tag}: {mast} = {aspect!r} (expected {want})"
        if ok:
            print(line)
        else:
            run.fail(line)


def check_mqtt_heads(run: Run, snap: Mapping[str, object], heads_mqtt: Mapping[str, str], tag: str) -> None:
    """Stop-like SML must not leave a live Green/Yellow on any mast head."""
    for mast, ihs in MAST_HEADS.items():
        wired = [ih for ih in ihs if re.fullmatch(r"IH\d+", ih)]    # only wired heads publish (ADR-024)
        aspect = aspect_of(snap, mast)
        if not wired or aspect is None:
            continue
        colors = [heads_mqtt.get(ih) for ih in wired]
        if aspect in STOPLIKE:
            if not all(c in STOP_HEAD for c in colors):
                run.fail(f"[FAIL] {tag}: {mast} SML={aspect!r} but MQTT {dict(zip(wired, colors))}")
        elif aspect and not any(c not in STOP_HEAD for c in colors):
            run.fail(f"[FAIL] {tag}: {mast} SML={aspect!r} but MQTT all stop-like {dict(zip(wired, colors))}")


def observe(run: Run, tag: str, desc: str, expect: Mapping[str, Want] | None = None) -> None:
    time.sleep(SETTLE)
    snap = jmri_snapshot()
    heads_mqtt = mqtt_heads()
    blob = f"## {tag}\n{desc}\n{render(snap, heads_mqtt)}\n"
    run.notes.append(blob)
    print(blob)
    if expect:
        check(run, snap, tag, expect)
    check_mqtt_heads(run, snap, heads_mqtt, tag)


@dataclass(frozen=True)
class Set:
    """One retained state the QA drives: a switch (TO) or an occupancy block (OCC)."""
    what: Literal["turnout", "occupancy"]
    name: str
    state: str


def turnout(sw: str, state: str) -> Set:
    return Set("turnout", sw, state)


def occupancy(block: str, state: str) -> Set:
    return Set("occupancy", block, state)


def apply(change: Set) -> None:
    (set_to if change.what == "turnout" else set_occ)(change.name, change.state)


@dataclass(frozen=True)
class Step:
    """Drive `before`, wait, read the masts and check `expect`, then drive `after`."""
    tag: str
    desc: str
    expect: Mapping[str, Want]
    before: tuple[Set, ...] = ()
    after: tuple[Set, ...] = ()


REST = (tuple(turnout(sw, st) for sw, st in (
    ("113", "CLOSED"), ("114", "CLOSED"), ("115", "CLOSED"), ("110", "CLOSED"), ("111", "CLOSED"),
    ("112", "THROWN"), ("117", "CLOSED"), ("100", "CLOSED"), ("102", "CLOSED")))
    + tuple(occupancy(blk, "INACTIVE") for blk in OCC))

SCENARIO = (
    Step("qa00_rest", "All occ clear; 113/114/115/110/111/117/100/102 CLOSED, 112 THROWN (field rest).", {
        "Mast 68": "nonstop",
        "Mast 67": "nonstop",
        "Mast 40LB": "nonstop",      # dest Mast 24L: Sw115+Sw111 closed
        "Mast 38LA": "nonstop",      # dest Mast 34L: Sw113/114 closed
        "Mast 40LA": "stop",         # needs Sw115 thrown
        "Mast 38LB": "stop",         # needs Sw114 thrown
        "Mast 32R": "stop",          # needs Sw110 thrown
        "Mast 8LB": "nonstop",       # dest Mast 6LB: Sw117 closed
    }, before=REST),
    # Princess 115 / McKees Rocks / K-1 leg
    Step("qa01_115_thrown", "115 THROWN: main runs via K-1 balloon; McKees Rocks cut off.", {
        "Mast 40LB": "stop",
        "Mast 40LA": "Diverging Clear",   # diverging route (115 thrown), dest Mast 24L non-Stop: bottom head green
        "Mast 67": "nonstop",             # dest Mast 40LA after Discover
        "Mast 36RA": "nonstop",           # dest Mast 67 via 113C+115T
    }, before=(turnout("115", "THROWN"),)),
    Step("qa02_115T_wme_occ", "115 THROWN + West Ext occupied: Rocks-main path fouled.", {"Mast 40LA": "stop"},
         before=(occupancy("West Ext", "ACTIVE"),),
         after=(occupancy("West Ext", "INACTIVE"), turnout("115", "CLOSED"))),
    # Princess 114 / McKeesport / K-2 leg + A48 balloon
    Step("qa03_114_thrown", "114 THROWN: main runs via K-2 balloon; McKeesport cut off.", {
        "Mast 38LB": "nonstop",
        "Mast 36RB": "nonstop",           # dest Mast 68 via 113C+114T
    }, before=(turnout("114", "THROWN"),)),
    Step("qa04_114T_mckeesport_occ", "114 THROWN + K-2 balloon occupied (A48 boundary test).", {
        "Mast 68": "stop",
        "Mast 36RB": "stop",
    }, before=(occupancy("K-2", "ACTIVE"),), after=(occupancy("K-2", "INACTIVE"), turnout("114", "CLOSED"))),
    # McKeesport occupancy path
    Step("qa05_east_lead_occ", "East Lead occupied: McKeesport's route to East Lead mast fouled; McKees Rocks "
         "(via 111a) unaffected.", {
             "Mast 38LA": "stop",
             "Mast 40LB": "nonstop",
         }, before=(occupancy("East Lead", "ACTIVE"),), after=(occupancy("East Lead", "INACTIVE"),)),
    # OS 110 dwarf ('always red' regression)
    Step("qa06_110T_112C", "110 THROWN + 112 CLOSED: ladder move OS110 -> East Lead -> 113a lined.",
         {"Mast 32R": "nonstop"}, before=(turnout("112", "CLOSED"), turnout("110", "THROWN"))),
    Step("qa07_110_closed", "110 CLOSED again: OS 110 dwarf back to Stop.", {"Mast 32R": "stop"},
         before=(turnout("110", "CLOSED"),), after=(turnout("112", "THROWN"),)),
    # 117 / 117b
    Step("qa08_eme_occ", "East Ext occupied: 117b's route to Plane East Ext fouled.", {"Mast 8LB": "stop"},
         before=(occupancy("East Ext", "ACTIVE"),), after=(occupancy("East Ext", "INACTIVE"),)),
    Step("qa09_117_thrown", "117 THROWN: T6 mast routes to Plane East Ext; 117b cut off.", {
        "Mast 8LA": "nonstop",
        "Mast 8LB": "stop",
    }, before=(turnout("117", "THROWN"),), after=(turnout("117", "CLOSED"),)),
    # Brick/Plane 100 & 102
    Step("qa10_100_thrown", "100 THROWN + 102 CLOSED: Plane East Ext lined to EE West Main West.", {
        "Mast 6LB": "nonstop",
        "Mast 2L": "nonstop",             # dest Mast 8RB via 100T+102C
        "Mast 24L": "Clear",
    }, before=(turnout("100", "THROWN"),)),
    Step("qa11_100T_main_west_occ", "100 THROWN + Main West occupied: Plane East Ext route fouled.",
         {"Mast 6LB": "stop"}, before=(occupancy("Main West", "ACTIVE"),),
         after=(occupancy("Main West", "INACTIVE"), turnout("100", "CLOSED"))),
    Step("qa12_back_to_rest", "Everything back at field rest.", {
        "Mast 40LB": "nonstop",
        "Mast 38LA": "nonstop",
        "Mast 8LB": "nonstop",
    }),
)


def run_scenario(run: Run, steps: Sequence[Step] = SCENARIO) -> None:
    for st in steps:
        for change in st.before:
            apply(change)
        observe(run, st.tag, st.desc, st.expect)
        for change in st.after:
            apply(change)


def main() -> int:
    try:
        for name in ("mosquitto_pub", "mosquitto_sub"):
            client(name)
    except QAError as err:
        print(f"run_native_sml_qa: {err}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    print("capturing retained baseline…", flush=True)
    baseline = capture_baseline()
    (OUT / "native_sml_qa_baseline.json").write_text(json.dumps(baseline, indent=1))
    print(f"captured {len(baseline)} retained topics")
    run = Run()
    try:
        run_scenario(run)
    finally:
        print("restoring retained baseline…")
        for topic, payload in baseline.items():
            pub(topic, payload)
        time.sleep(SETTLE)
        observe(run, "qa99_restored", "Retained baseline restored.")
    (OUT / "native_sml_qa_notes.md").write_text("\n".join(run.notes))
    print("wrote", OUT / "native_sml_qa_notes.md")
    if run.failures:
        print("\n%d FAILURE(S):" % len(run.failures))
        for f in run.failures:
            print(" ", f)
        return 1
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
