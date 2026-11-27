#!/usr/bin/env python3
"""Native-SML mimic QA: drive retained MQTT states, assert mast aspects via JMRI JSON.

Covers the masts in LIVE_MASTS. Writes native_sml_qa_notes.md and the baseline here (gitignored run output).
Never publishes track/cmd/*. Captures retained baseline and restores it.

    python3 tools/mqtt-mimic/qa/run_native_sml_qa.py           run the steps (the broker and JMRI JSON)
    python3 tools/mqtt-mimic/qa/run_native_sml_qa.py --list    print the steps and their messages; publish nothing

The steps are jmri/layouts/hart/data/native_sml_qa.csv, read through hartlib.sml_qa: each names the staging devices
it drives by device ID, and their LCOS MQTT addresses and feedback sensors come from the device master.

Live CATS ABS is HOLD_ONLY on the same JMRI masts (ADR-005 names).
CATS-prefixed twin masts are gone, so this compares SML aspect vs MQTT head
appearance (what CATS ABS paints / LCOS sees). `held` is CATS ABS Hold.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

OUT = Path(__file__).resolve().parent
# where the mosquitto clients are looked for: PATH, then MacPorts' bin folder (the Mac's install)
CLIENT_DIRS = (*os.environ.get("PATH", "").split(os.pathsep), "/opt/local/bin")
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, level_masts, paths, railroad, sml_qa, tables as tables_mod  # noqa: E402
from hartlib.hosts import jmri_json_url, mqtt_broker  # noqa: E402

ROOT = paths.REPO_ROOT
sys.path.insert(0, str(ROOT / "tools" / "audit"))
from check_wiring_crosswalk import read_tables  # noqa: E402

HOST = mqtt_broker()
JMRI_JSON = jmri_json_url()
LOCAL_JMRI_JSON = "http://127.0.0.1:12080/json"

TABLES = paths.TABLES_XML
SETTLE = 4.5
# the topic of each kind of retained state the QA drives (LCOS status topics, never a command topic)
TURNOUT_TOPIC = "track/turnout/{}"
SENSOR_TOPIC = "track/sensor/{}"
HEAD_TOPICS = "track/signalhead/#"      # every signal head's appearance, read only


class QAError(Exception):
    """The QA cannot start: a mosquitto client is missing, tables.xml has a head mast it cannot read, or the steps
    file or a device it names is not in its shape (hartlib.sml_qa.QAError)."""


def client(name: str) -> str:
    """The path of a mosquitto client (mosquitto_pub, mosquitto_sub); QAError naming the folders searched."""
    found = shutil.which(name, path=os.pathsep.join(CLIENT_DIRS))
    if found is None:
        raise QAError(f"{name} is not in PATH or /opt/local/bin; install the mosquitto clients")
    return found


class SubscribeError(QAError):
    """mosquitto_sub exited with an error (the broker refused or did not answer), not with its -W timeout."""


# mosquitto_sub's exit codes that end a read normally: 0, and 27 when the -W timeout ends it ("Timed out waiting for
# message", man mosquitto_sub, EXIT STATUS): a topic with no retained message, or the timeout ending a wildcard read.
SUB_DONE = (0, 27)


def subscribe(topic: str, *options: str) -> str:
    """mosquitto_sub's output for one topic filter (-v: "topic payload" lines); SubscribeError naming the topic, the
    exit code and what the client said when it exits with any code but SUB_DONE."""
    p = subprocess.run([client("mosquitto_sub"), "-h", HOST, "-t", topic, *options, "-W", "2", "-v"],
                       capture_output=True, text=True)
    if p.returncode not in SUB_DONE:
        said = p.stderr.strip() or "nothing on stderr"
        raise SubscribeError(f"mosquitto_sub -h {HOST} on {topic} exited {p.returncode}: {said}")
    return p.stdout


STOPLIKE = {"Stop", "Unlit", "Dark", "Held", None, ""}

Write = tuple[str, str]      # (topic, payload) of one retained message


def pub(topic: str, payload: str) -> None:
    subprocess.check_call(
        [client("mosquitto_pub"), "-h", HOST, "-r", "-t", topic, "-m", payload],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def load_steps(path: Path = sml_qa.PATH) -> tuple[tuple[sml_qa.Step, ...], dict[str, sml_qa.Drive]]:
    """The steps (hartlib.sml_qa) and the devices they drive, by ID from the device master; QAError on a bad file,
    row or device."""
    try:
        steps = sml_qa.read(path)
        return steps, sml_qa.drives(steps, path=path)
    except (sml_qa.QAError, devices.DevicesError) as exc:
        raise QAError(str(exc)) from exc


def writes(change: sml_qa.Change, drives: Mapping[str, sml_qa.Drive]) -> list[Write]:
    """The retained messages that set one change: an occupancy sensor's state; for a turnout, its feedback sensors
    first (normal ACTIVE when closed, reverse ACTIVE when thrown) when it has them, then its status."""
    d = drives[change.device]
    if d.layer == "occupancy":
        return [(SENSOR_TOPIC.format(d.address), change.state)]
    out: list[Write] = []
    if d.feedback:
        thrown = change.state == "THROWN"
        normal, reverse = d.feedback
        out += [(SENSOR_TOPIC.format(normal), "INACTIVE" if thrown else "ACTIVE"),
                (SENSOR_TOPIC.format(reverse), "ACTIVE" if thrown else "INACTIVE")]
    return out + [(TURNOUT_TOPIC.format(d.address), change.state)]


def touched_topics(drives: Mapping[str, sml_qa.Drive]) -> list[str]:
    """Every topic the steps write, in the order the baseline captures and restores them: the turnouts by address,
    their feedback sensors in the same order, then the occupancy sensors in the order the steps first name them
    (`drives` keeps that order)."""
    turnouts = sorted((d for d in drives.values() if d.layer == "turnout"), key=lambda d: int(d.address))
    return ([TURNOUT_TOPIC.format(d.address) for d in turnouts]
            + [SENSOR_TOPIC.format(a) for d in turnouts for a in d.feedback or ()]
            + [SENSOR_TOPIC.format(d.address) for d in drives.values() if d.layer == "occupancy"])


def capture_baseline(topics: Sequence[str]) -> dict:
    """Read current retained value of every topic we will touch (none for a topic with no retained message)."""
    base: dict[str, str] = {}
    for topic in topics:
        line = subscribe(topic, "-C", "1").strip()
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
MAST_HEADS: dict[str, tuple[str, ...]] = {}     # filled by main() from load_mast_heads()


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
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError, KeyError, TypeError) as err:
            print(f"JMRI JSON at {base}: {err}", file=sys.stderr)
    print("no JMRI JSON: the aspects come from the MQTT heads", file=sys.stderr)
    return snap_from_mqtt(mqtt_heads())


def mqtt_heads() -> dict[str, str]:
    """Each signal head's retained colour, by head system name: what arrives before subscribe's 2-second timeout."""
    out = {}
    for line in subscribe(HEAD_TOPICS).splitlines():
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


def check(run: Run, snap: Mapping[str, object], tag: str, expect: Iterable[tuple[str, Want]]) -> None:
    for mast, want in expect:
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


def observe(run: Run, tag: str, desc: str, expect: Iterable[tuple[str, Want]] = ()) -> None:
    time.sleep(SETTLE)
    snap = jmri_snapshot()
    heads_mqtt = mqtt_heads()
    blob = f"## {tag}\n{desc}\n{render(snap, heads_mqtt)}\n"
    run.notes.append(blob)
    print(blob)
    check(run, snap, tag, expect)
    check_mqtt_heads(run, snap, heads_mqtt, tag)


def apply(change: sml_qa.Change, drives: Mapping[str, sml_qa.Drive]) -> None:
    for topic, payload in writes(change, drives):
        pub(topic, payload)


def run_scenario(run: Run, steps: Sequence[sml_qa.Step], drives: Mapping[str, sml_qa.Drive]) -> None:
    for st in steps:
        for change in st.before:
            apply(change, drives)
        observe(run, st.tag, st.desc, st.expect)
        for change in st.after:
            apply(change, drives)


def step_list(steps: Sequence[sml_qa.Step], drives: Mapping[str, sml_qa.Drive]) -> list[str]:
    """The lines --list prints: the topics the run captures and restores, then each step's description, the masts
    it checks and the retained messages it writes before and after the check."""
    topics = touched_topics(drives)
    lines = [f"touched {len(topics)}", *(f"  {t}" for t in topics)]
    for st in steps:
        lines += [f"## {st.tag}", st.desc, *(f"  expect {mast} = {want}" for mast, want in st.expect)]
        for label, changes in (("before", st.before), ("after", st.after)):
            lines += [f"  {label} {topic} {payload}" for change in changes for topic, payload in writes(change, drives)]
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--list", action="store_true",
                    help="print the steps and the retained messages each writes; nothing is published or read")
    args = ap.parse_args(argv)
    try:
        steps, drives = load_steps()
        if args.list:
            print("\n".join(step_list(steps, drives)))
            return 0
        for name in ("mosquitto_pub", "mosquitto_sub"):
            client(name)
        MAST_HEADS.update(load_mast_heads())
    except QAError as err:
        print(f"run_native_sml_qa: {err}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    print("capturing retained baseline…", flush=True)
    try:
        baseline = capture_baseline(touched_topics(drives))
    except SubscribeError as err:       # nothing published yet
        print(f"run_native_sml_qa: baseline not captured, nothing driven: {err}", file=sys.stderr)
        return 2
    (OUT / "native_sml_qa_baseline.json").write_text(json.dumps(baseline, indent=1))
    print(f"captured {len(baseline)} retained topics")
    run = Run()
    try:
        try:
            run_scenario(run, steps, drives)
        finally:
            print("restoring retained baseline…")
            for topic, payload in baseline.items():
                pub(topic, payload)
            time.sleep(SETTLE)
            observe(run, "qa99_restored", "Retained baseline restored.")
    except SubscribeError as err:       # the baseline was published back before this
        run.notes.append(f"## stopped\nA read failed, so the run stopped here: {err}\n")
        report(run)
        print(f"run_native_sml_qa: {err}", file=sys.stderr)
        return 2
    if report(run):
        return 1
    print("\nALL CHECKS PASSED")
    return 0


def report(run: Run) -> bool:
    """Write the notes file and print the failed checks; True when any check failed."""
    (OUT / "native_sml_qa_notes.md").write_text("\n".join(run.notes))
    print("wrote", OUT / "native_sml_qa_notes.md")
    if run.failures:
        print("\n%d FAILURE(S):" % len(run.failures))
        for f in run.failures:
            print(" ", f)
    return bool(run.failures)


if __name__ == "__main__":
    sys.exit(main())
