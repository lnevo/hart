"""The crew master, ops/hart-ops/data/crew.json, and the views built from it (ADR-039, lane L5).

The master holds the crew jobs (key: `code`, the train symbol for a crew job), the destination colors (key: `id`), the
TT-23 timetable, the spot sheet, EQ-01 and the station map text. Two kinds of reader use it:

- build_crew_json.py writes www/data/crew.json from site_view(): the master less every `docx` object, with the spot
  sheet's industry names and anchors from ops/hart-ops/data/industries.csv, a job's `site_note` (a sentence only the
  site prints) and the yardmaster and dispatcher rules appended to their summaries, each lineup row's route put before its action, and the schematic's revision and date
  from the title block (hartlib.map_revision.fields).
- the rebuild_*.py docx scripts read the jobs, colors and timetable through the functions below. A `docx` object in
  the master holds what only the printed sheet uses (a photo, a legend order) or wording the sheet prints
  differently from the site; each such wording is an open owner question (lane L5, 2026-11-25).

Standard library only, so the site build and the checks import it without python-docx.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

PUB = Path(__file__).resolve().parent
REPO = PUB.parents[2]
MASTER = REPO / "ops/hart-ops/data/crew.json"
INDUSTRIES = REPO / "ops/hart-ops/data/industries.csv"


def load(path: Path = MASTER) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_industries(path: Path = INDUSTRIES) -> dict[str, dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return {row["industry_id"]: row for row in csv.DictReader(fh)}


def job(master: dict, job_id: str) -> dict:
    for j in master["jobs"]:
        if j["id"] == job_id:
            return j
    raise KeyError(f"{MASTER.name}: no job {job_id!r}")


def _drop_docx(value):
    if isinstance(value, dict):
        return {k: _drop_docx(v) for k, v in value.items() if k != "docx"}
    if isinstance(value, list):
        return [_drop_docx(v) for v in value]
    return value


def _site_job(j: dict) -> dict:
    out = {}
    for k, v in j.items():
        if k in ("rules", "site_note"):
            continue
        if k == "summary":
            v = " ".join([v, *([j["site_note"]] if j.get("site_note") else []), *j.get("rules", [])])
        if k == "lineup":
            v = [{"n": r["n"], "train": r["train"], "action": f"{r['route']} {r['action']}",
                  **({"colors": r["colors"]} if "colors" in r else {})} for r in v]
        out[k] = v
    return out


NOTE = ("Built from ops/hart-ops/data/crew.json and ops/hart-ops/data/industries.csv by "
        "ops/hart-ops/publications/build_crew_json.py (ADR-039). Edit those, then rebuild; never edit this file.")


def site_view(master: dict, industries: dict[str, dict[str, str]], schematic: tuple[str, str]) -> dict:
    """The content of www/data/crew.json. schematic is (revision, effective) from the title block."""
    m = _drop_docx(master)
    out: dict = {"_note": NOTE}
    for key, value in m.items():
        if key == "_about":
            continue
        if key == "spotsheet":
            value = dict(value)
            rows = []
            for ind in value["industries"]:
                row = industries.get(ind["industry_id"])
                if row is None:
                    raise ValueError(f"{MASTER.name}: spot sheet industry {ind['industry_id']!r} is not in {INDUSTRIES.name}")
                rows.append({"id": row["slug"], "name": row["name"],
                             **{k: v for k, v in ind.items() if k != "industry_id"}})
            value["industries"] = rows
        elif key == "jobs":
            value = [_site_job(j) for j in value]
        elif key == "schematic":
            value = {**value, "revision": schematic[0], "effective": schematic[1]}
        out[key] = value
    return out


def dump(data) -> str:
    """The file text: the format hartlib.map_revision writes too."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# ---- the docx views -------------------------------------------------------------------------------------------

def hex6(color: str) -> str:
    """'#0000CD' -> '0000CD', '#fff' -> 'FFFFFF'."""
    h = color.lstrip("#").upper()
    return "".join(c * 2 for c in h) if len(h) == 3 else h


def color_key(master: dict) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(interchange, island) swatches of the abridged color key: (fill, label) in the master's order."""
    def rows(group):
        return [(hex6(c["hex"]), c.get("docx", {}).get("key_label", c["dest"]))
                for c in master["colors"] if c["group"] == group]
    return rows("interchange"), rows("island")


def tt23_rows(master: dict) -> list[tuple[str, str, str]]:
    return [tuple(r) for r in master["timetable"]["rows"]]


def tt23_back_page(master: dict) -> dict[str, str]:
    """The subtitle and note the back page of the crew, YM and DS sheets prints under its timetable."""
    return master["timetable"]["docx"]


def publication(j: dict) -> dict[str, str]:
    return {"title": j["title"], "pub_id": j["pub"], "revision": j["revision"], "effective": j["effective"]}


def docx_name(j: dict) -> str:
    """The docx file name, from the job's source link (../docs/ops/<name>)."""
    return Path(j["source"]).name


def crews(master: dict) -> list[dict]:
    """The crew jobs as rebuild_crew_instructions prints them (photo is a file name under jmri/resources/roster)."""
    out = []
    for j in master["jobs"]:
        if j["kind"] != "crew":
            continue
        d = j.get("docx", {})
        engine = j["engine"]["label"] if j.get("engine") else ""
        out.append({
            "train": j["code"],
            "pub_id": j["pub"],
            "file": docx_name(j),
            "subtitle": j["name"],
            "engine": d.get("engine", engine.replace(" · ", "  ·  ")),
            "photo": d.get("photo"),
            "intro": d.get("intro", j["summary"]),
            "steps": d.get("steps", j["steps"]),
            "publication": publication(j),
        })
    return out


def block_legend(master: dict) -> list[tuple[str, str, str, str, str]]:
    """YM-01's blocking list: (label, fill, text, destination, block), in the order the sheet prints."""
    ym = job(master, "yardmaster")["docx"]
    colors = {c["id"]: c for c in master["colors"]}
    rows = [(colors[i]["label"], hex6(colors[i]["hex"]), hex6(colors[i]["ink"]), colors[i]["dest"], colors[i]["train"])
            for i in ym["legend"]]
    rows += [(e["label"], e["fill"], e["text"], e["dest"], e["block"]) for e in ym.get("legend_extra", [])]
    return rows


def yard_sequence(master: dict) -> list[tuple[str, str, str]]:
    """YM-01's sequence: (n, train, action), the action ending in its colors' names unless the sheet words it."""
    colors = {c["id"]: c for c in master["colors"]}
    out = []
    for r in job(master, "yardmaster")["sequence"]:
        names = ", ".join(colors[c]["label"].title() for c in r.get("colors", []))
        action = r.get("docx", {}).get("action") or (f"{r['action']} ({names})" if names else r["action"])
        out.append((r["n"], r["train"], action))
    return out


def lineup(master: dict) -> list[tuple[str, str, str, str]]:
    """DS-01's lineup: (n, train, route, action)."""
    return [(r["n"], r["train"], r["route"], r["action"]) for r in job(master, "dispatcher")["lineup"]]


SMALL = {"a", "an", "and", "at", "for", "of", "on", "the", "to"}


def heading_case(text: str) -> str:
    """'2.1 Preparing the scale' -> '2.1 Preparing the Scale': EQ-01 prints its part headings in title case."""
    words = text.split(" ")
    return " ".join(w if (i and w in SMALL) else re.sub(r"[A-Za-z]+", lambda m: m[0][0].upper() + m[0][1:], w)
                    for i, w in enumerate(words))


def scale_blocks(master: dict) -> list[dict]:
    """EQ-01's body as blocks (kind h1, intro, h2 or steps), without layout: the script adds that by section."""
    sc = master["scale"]
    blocks: list[dict] = []
    for n, sec in enumerate(sc["sections"]):
        blocks.append({"kind": "h1", "text": sec["heading"].upper()})
        if n == 0:
            blocks.append({"kind": "intro", "text": sc["summary"]})
        for part in sec["parts"]:
            blocks.append({"kind": "h2", "text": heading_case(part["h"])})
            lead = part.get("docx", {}).get("lead_items", 0)
            for item in part["items"][:lead]:
                blocks.append({"kind": "intro", "text": item})
            blocks.append({"kind": "steps", "items": part["items"][lead:]})
    return blocks
