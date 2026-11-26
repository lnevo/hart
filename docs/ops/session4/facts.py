"""Facts for the session 4 designs, read from the repo's source files (never typed in here).

Control points: jmri/layouts/hart/data/schematic/interlockings.csv (all levels).
Jobs: www/data/briefing.json, section "jobs" (the crew board order the primer prints).
Job colours and train symbols: ops/hart-ops/data/crew.json and ops/hart-ops/data/trains.csv.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INTERLOCKINGS = ROOT / "jmri/layouts/hart/data/schematic/interlockings.csv"
BRIEFING = ROOT / "www/data/briefing.json"
CREW = ROOT / "ops/hart-ops/data/crew.json"
TRAINS = ROOT / "ops/hart-ops/data/trains.csv"
LEVEL_NAMES = {"1": "Staging", "2": "Main", "3": "Upper"}
# The primer calls the yardmaster and dispatcher jobs by title; crew.json codes them by sheet.
ALIAS = {"Yardmaster": "YM-01", "Dispatcher": "DS-01"}


def control_points() -> list[dict]:
    """One dict per interlocking: id, name, level name, switch numbers (strings), in file order."""
    with INTERLOCKINGS.open(newline="") as f:
        return [{"id": r["cp_id"], "name": r["interlocking"], "level": LEVEL_NAMES[r["level"]],
                 "switches": [s.strip() for s in r["switches"].split(",")]} for r in csv.DictReader(f)]


def board_jobs() -> list[dict]:
    """The jobs of the primer's crew board, in its order, each with its colour ids where crew.json has the job."""
    sections = json.loads(BRIEFING.read_text())["sections"]
    jobs = next(s for s in sections if s.get("id") == "jobs")["jobs"]
    colours = {j["code"]: j.get("colors", []) for j in json.loads(CREW.read_text())["jobs"]}
    return [{"code": j["code"], "name": j["name"], "colors": colours.get(ALIAS.get(j["code"], j["code"]), [])}
            for j in jobs]


def colour_key() -> list[dict]:
    """The destination colours of crew.json: id, label, hex, ink, dest, train."""
    return json.loads(CREW.read_text())["colors"]


def lineup() -> list[dict]:
    """The DS-01 lineup trains in lineup order (trains.csv rows whose notes carry a DS-01 number)."""
    with TRAINS.open(newline="") as f:
        return [r for r in csv.DictReader(f) if r["notes"].startswith("DS-01")]
