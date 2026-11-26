#!/usr/bin/env python3
"""Generate card_review.html — local review UI for HART car cards."""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from engine_lookup import (
    build_locomotive_description,
    is_locomotive_row,
    load_engine_roster as load_eng_roster,
    match_engine as match_eng,
    manufacturer_for_model,
)
from card_description import build_freight_description, normalize_car_type, format_type_label

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
DATA = BASE / "data"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
METADATA_CSV = DATA / "image_metadata.csv"
CAR_ROSTER_XML = DATA / "OperationsCarRoster.xml"
ENGINE_ROSTER_XML = DATA / "OperationsEngineRoster.xml"
CARD_FILL_DIR = BASE / "CarImagesCardFill"
OUTPUT = OUTPUT_DIR / "card_review.html"
IMAGE_DIR = CARD_FILL_DIR

ROAD_DISPLAY = {
    "NW": "N&W",
    "BO": "B&O",
    "PRR": "PRR",
    "NYC": "NYC",
    "ATSF": "ATSF",
    "CBQ": "CB&Q",
    "GN": "GN",
    "MILW": "MILW",
    "WP": "WP",
    "WM": "WM",
    "RDG": "RDG",
    "EL": "EL",
    "CO": "C&O",
    "KSMX": "KSMX",
    "GATX": "GATX",
    "UTLX": "UTLX",
    "URTX": "URTX",
    "SHPX": "SHPX",
    "REX": "REX",
    "URR": "URR",
    "WLE": "WLE",
    "MSTL": "MSTL",
    "MOW": "MOW",
    "CSX": "CSX",
    "CWRY": "Ohio Central",
}

# Manifest reporting marks -> engine roster roadName
ENGINE_ROAD_ALIASES = {
    "OC": "CWRY",
    "OHIO CENTRAL": "CWRY",
    "B&O": "BO",
    "C&O": "CO",
    "CR": "CR",
    "CONRAIL": "CR",
    "CSX": "CSX",
}


def load_car_roster() -> tuple[list[str], list[str], dict[str, dict]]:
    root = ET.parse(CAR_ROSTER_XML).getroot()
    roads = sorted({el.get("name", "") for el in root.findall("./roads/road") if el.get("name")})
    types = sorted({el.get("name", "") for el in root.findall("./types/type") if el.get("name")})
    cars: dict[str, dict] = {}
    for el in root.findall("./cars/car"):
        rid = el.get("id", "")
        road = el.get("roadName", "")
        cars[rid] = {
            "roster_id": rid,
            "roster_road": road,
            "road_number": el.get("roadNumber", ""),
            "car_type": el.get("type", ""),
            "length_ft": el.get("length", ""),
        }
    return roads, types, cars


def load_engine_roster() -> tuple[list[str], list[str], dict[str, dict], dict[tuple[str, str], dict], list[str]]:
    root = ET.parse(ENGINE_ROSTER_XML).getroot()
    roads = sorted({el.get("roadName", "") for el in root.findall("./engines/engine") if el.get("roadName")})
    types = sorted({el.get("name", "") for el in root.findall("./types/type") if el.get("name")})
    models = sorted({el.get("name", "") for el in root.findall("./models/model") if el.get("name")})
    engines: dict[str, dict] = {}
    by_key: dict[tuple[str, str], dict] = {}
    for el in root.findall("./engines/engine"):
        rid = el.get("id", "")
        road = el.get("roadName", "")
        num = el.get("roadNumber", "")
        rec = {
            "engine_roster_id": rid,
            "roster_road": road,
            "road_number": num,
            "engine_type": el.get("type", ""),
            "model": el.get("model", ""),
            "length_ft": el.get("length", ""),
            "hp": el.get("hp", ""),
        }
        engines[rid] = rec
        by_key[(road, num)] = rec
    extra_types = types + ["Locomotive", "Streetcar"]
    return roads, extra_types, engines, by_key, models


def display_road(marks: str, roster_road: str = "") -> str:
    mk = marks.strip()
    if mk:
        return mk
    if roster_road:
        return ROAD_DISPLAY.get(roster_road, roster_road)
    return ""


def build_description(
    *,
    color: str,
    car_type: str,
    length_ft: str,
    model: str = "",
    is_engine: bool = False,
) -> str:
    parts: list[str] = []
    if color:
        parts.append(color)
    if is_engine and model:
        parts.append(model)
    elif car_type:
        parts.append(format_type_label(car_type))
    if length_ft:
        parts.append(f"{length_ft}'")
    return " · ".join(parts) if parts else ""


def match_engine(row: dict, by_key: dict[tuple[str, str], dict]) -> dict | None:
    marks = (row.get("reporting_marks") or row.get("road_name") or "").strip()
    number = (row.get("road_number") or "").strip()
    if not number:
        return None
    norm_marks = re.sub(r"[^A-Z0-9&]", "", marks.upper())
    candidates = [norm_marks]
    alias = ENGINE_ROAD_ALIASES.get(marks.upper()) or ENGINE_ROAD_ALIASES.get(norm_marks)
    if alias:
        candidates.append(alias)
    for road in candidates:
        hit = by_key.get((road, number))
        if hit:
            return hit
    return None


def resolve_image(row: dict) -> str:
    stem = Path(row.get("source_image", "")).stem
    if stem:
        p = IMAGE_DIR / f"{stem}.png"
        if p.exists():
            return f"{IMAGE_DIR.name}/{stem}.png"
    rel = row.get("cropped_image", "").strip()
    return rel if rel else ""


def load_rows() -> list[dict]:
    _, _, car_roster = load_car_roster()
    _, eng_by_key = load_eng_roster()

    rows: list[dict] = []
    with METADATA_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            src = row.get("source_image", "")
            car = car_roster.get(row.get("roster_id", "").strip())
            engine = match_eng(row, eng_by_key)

            is_engine = bool(engine) or row.get("car_type", "") in ("Locomotive", "Streetcar")
            road = display_road(
                row.get("reporting_marks") or row.get("road_name", ""),
                (car or {}).get("roster_road") or (engine or {}).get("roster_road", ""),
            )
            if engine and road in ("", "?", "OC") and engine["roster_road"] == "CWRY":
                road = ROAD_DISPLAY.get("CWRY", "Ohio Central")
            elif engine and road in ("", "?"):
                road = ROAD_DISPLAY.get(engine["roster_road"], engine["roster_road"])

            ctype = normalize_car_type(row.get("car_type", "").strip())
            if engine:
                ctype = engine.get("engine_type") or "Diesel"
                if ctype == "Engine":
                    ctype = "Diesel"

            length = ""
            if car:
                length = car.get("length_ft", "")
            elif engine:
                length = engine.get("length_ft", "")
            elif row.get("roster_length_ft"):
                length = row["roster_length_ft"]

            if row.get("full_name", "").strip():
                desc = row["full_name"].strip()
            elif is_locomotive_row(row) or engine:
                desc = build_locomotive_description(engine, row)
            else:
                merged = dict(row)
                if car and not merged.get("roster_length_ft"):
                    merged["roster_length_ft"] = car.get("length_ft", "")
                if car and not merged.get("car_type"):
                    merged["car_type"] = car.get("car_type", "")
                desc = build_freight_description(merged, car)

            rows.append(
                {
                    "source_image": src,
                    "image": resolve_image(row),
                    "car_type": ctype or row.get("car_type", ""),
                    "road_name": road,
                    "road_number": row.get("road_number", "") or (car or {}).get("road_number", "") or (engine or {}).get("road_number", ""),
                    "description": desc,
                    "color": row.get("color", ""),
                    "manufacturer": (engine or {}).get("manufacturer") or manufacturer_for_model((engine or {}).get("model", "")),
                    "roster_id": row.get("roster_id", ""),
                    "engine_roster_id": (engine or {}).get("engine_roster_id", ""),
                    "engine_model": (engine or {}).get("model", ""),
                    "length_ft": length,
                    "notes": row.get("notes", ""),
                    "is_engine": bool(engine),
                }
            )
    return rows


def collect_lookups(rows: list[dict]) -> tuple[list[str], list[str]]:
    _, car_types, _ = load_car_roster()
    eng_roads, eng_types, _, _, _ = load_engine_roster()

    types = sorted(
        {
            normalize_car_type(t)
            for t in car_types + eng_types + [r["car_type"] for r in rows if r["car_type"]]
        }
        - {""}
    )
    roads = sorted(
        set(ROAD_DISPLAY.values())
        | set(ROAD_DISPLAY.keys())
        | set(eng_roads)
        | {ROAD_DISPLAY.get(r, r) for r in eng_roads}
        | {r["road_name"] for r in rows if r["road_name"]}
        | {"Ohio Central", "Conrail", "Union", "RMLI", "TTC", "RMP", "CR", "OC", "CSX"}
    )
    return types, roads


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HART Car Card Review</title>
<style>
  :root {
    --bg: #f4f1ea;
    --card: #fff;
    --ink: #1a1a1a;
    --muted: #666;
    --line: #ccc;
    --accent: #2c5282;
    --changed: #fff8e1;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    background: var(--bg);
    color: var(--ink);
  }
  header {
    position: sticky; top: 0; z-index: 10;
    background: #2d3748; color: #fff;
    padding: 12px 20px;
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
    box-shadow: 0 2px 8px rgba(0,0,0,.15);
  }
  header h1 { margin: 0; font-size: 1.1rem; flex: 1; }
  header label { font-size: .85rem; }
  header input, header select, header button {
    font: inherit; padding: 6px 10px; border-radius: 4px; border: 1px solid #718096;
  }
  header button { background: var(--accent); color: #fff; border-color: var(--accent); cursor: pointer; }
  header button.secondary { background: #4a5568; border-color: #4a5568; }
  .layout { display: grid; grid-template-columns: 280px 1fr; min-height: calc(100vh - 56px); }
  aside {
    background: #edf2f7; border-right: 1px solid var(--line);
    padding: 16px; overflow: auto;
  }
  aside h2 { margin: 0 0 8px; font-size: .95rem; }
  aside section { margin-bottom: 20px; }
  aside input[type=text] { width: 100%; margin-bottom: 6px; padding: 6px; }
  aside ul { list-style: none; padding: 0; margin: 0; max-height: 140px; overflow: auto; }
  aside li {
    display: flex; justify-content: space-between; align-items: center;
    padding: 4px 0; border-bottom: 1px solid #e2e8f0; font-size: .85rem;
  }
  aside li button { font-size: .75rem; padding: 2px 6px; }
  main { padding: 16px; overflow: auto; }
  .stats { color: var(--muted); font-size: .85rem; margin-bottom: 12px; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
  }
  .card {
    background: var(--card);
    border: 2px solid #333;
    border-radius: 4px;
    overflow: hidden;
    box-shadow: 0 2px 6px rgba(0,0,0,.08);
  }
  .card.changed { background: var(--changed); }
  .card-head {
    display: grid; grid-template-columns: 70px 1fr auto;
    align-items: center; gap: 8px;
    padding: 8px 10px; background: #d9d9d9;
    border-bottom: 1px solid var(--line);
    font-size: .8rem;
  }
  .card-head img.logo { width: 56px; height: auto; }
  .card-head .title { font-weight: bold; font-size: .75rem; line-height: 1.2; }
  .card-head .badge {
    border: 1px solid #333; padding: 4px 8px; font-size: .65rem;
    background: #fff; text-align: center;
  }
  .card-photo {
    margin: 8px; border: 1.5px solid #333; background: #eee;
    height: 160px; display: flex; align-items: center; justify-content: center;
    cursor: zoom-in; overflow: hidden;
  }
  .card-photo img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .card-photo .missing { color: var(--muted); font-size: .85rem; }
  .card-fields { padding: 8px 10px 12px; display: grid; gap: 8px; }
  .field { display: grid; grid-template-columns: 90px 1fr; gap: 6px; align-items: center; font-size: .85rem; }
  .field label { color: var(--muted); }
  .field input, .field select, .field textarea {
    width: 100%; font: inherit; padding: 5px 6px; border: 1px solid var(--line); border-radius: 3px;
  }
  .field textarea { min-height: 52px; resize: vertical; }
  .meta { font-size: .72rem; color: var(--muted); padding: 0 10px 8px; }
  .export-panel {
    margin-top: 24px; padding: 16px; background: #fff; border: 1px solid var(--line);
    border-radius: 6px;
  }
  .export-panel h2 { margin-top: 0; }
  .export-panel textarea {
    width: 100%; min-height: 180px; font-family: ui-monospace, monospace;
    font-size: .8rem; padding: 10px;
  }
  .export-panel p { color: var(--muted); font-size: .85rem; }
  #lightbox {
    display: none; position: fixed; inset: 0; z-index: 100;
    background: rgba(0,0,0,.88); align-items: center; justify-content: center;
    padding: 24px; cursor: zoom-out;
  }
  #lightbox.open { display: flex; }
  #lightbox img { max-width: 95vw; max-height: 95vh; object-fit: contain; box-shadow: 0 8px 32px rgba(0,0,0,.5); }
  @media (max-width: 900px) {
    .layout { grid-template-columns: 1fr; }
    aside { border-right: none; border-bottom: 1px solid var(--line); }
  }
</style>
</head>
<body>
<header>
  <h1>HART Car Card Review</h1>
  <label>Filter <input type="search" id="filter" placeholder="road, number, type…"></label>
  <label><input type="checkbox" id="changedOnly"> Changed only</label>
  <button type="button" id="btnRebuildDesc">Rebuild descriptions</button>
  <button type="button" id="btnExport" class="secondary">Update export</button>
</header>
<div class="layout">
  <aside>
    <section>
      <h2>Car / engine types</h2>
      <input type="text" id="newType" placeholder="Add type…">
      <button type="button" id="addType">Add</button>
      <ul id="typeList"></ul>
    </section>
    <section>
      <h2>Road names</h2>
      <input type="text" id="newRoad" placeholder="Add road name…">
      <button type="button" id="addRoad">Add</button>
      <ul id="roadList"></ul>
    </section>
    <section>
      <h2>Help</h2>
      <p style="font-size:.8rem;color:#4a5568;line-height:1.4">
        Open this file from the <strong>Car Cards</strong> folder so photos load.
        Edit fields, then copy the export JSON at the bottom and send it back to update the CSV.
      </p>
    </section>
  </aside>
  <main>
    <div class="stats" id="stats"></div>
    <div class="grid" id="grid"></div>
    <div class="export-panel">
      <h2>Export changes</h2>
      <p>Copy this JSON and paste it in chat to apply updates to <code>image_metadata.csv</code>.</p>
      <textarea id="exportBox" readonly></textarea>
      <button type="button" id="btnCopy">Copy to clipboard</button>
    </div>
  </main>
</div>
<div id="lightbox" title="Click to close"><img alt=""></div>
<script>
const DATA = __DATA_JSON__;

let carTypes = [...DATA.carTypes];
let roadNames = [...DATA.roadNames];
const originals = new Map(DATA.rows.map(r => [r.source_image, JSON.parse(JSON.stringify(r))]));
let rows = DATA.rows.map(r => ({ ...r }));

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
}

function options(list, selected) {
  return list.map(v => `<option value="${esc(v)}"${v===selected?' selected':''}>${esc(v)}</option>`).join('');
}

function isChanged(r) {
  const o = originals.get(r.source_image);
  if (!o) return true;
  return ['car_type','road_name','road_number','description','color'].some(k => (r[k]||'') !== (o[k]||''));
}

function renderLookupList(id, items, kind) {
  const ul = document.getElementById(id);
  ul.innerHTML = items.map(v => `
    <li><span>${esc(v)}</span>
      <button type="button" data-kind="${kind}" data-value="${esc(v)}">×</button>
    </li>`).join('');
}

function renderCards() {
  const q = document.getElementById('filter').value.trim().toLowerCase();
  const changedOnly = document.getElementById('changedOnly').checked;
  const grid = document.getElementById('grid');
  const visible = rows.filter(r => {
    if (changedOnly && !isChanged(r)) return false;
    if (!q) return true;
    const hay = [r.source_image,r.road_name,r.road_number,r.car_type,r.description,r.engine_model,r.notes].join(' ').toLowerCase();
    return hay.includes(q);
  });
  document.getElementById('stats').textContent =
    `${visible.length} of ${rows.length} cards · ${rows.filter(isChanged).length} changed`;
  grid.innerHTML = visible.map(r => {
    const ch = isChanged(r) ? ' changed' : '';
    const img = r.image
      ? `<img src="${esc(r.image)}" alt="${esc(r.source_image)}" data-full="${esc(r.image)}">`
      : `<span class="missing">No image</span>`;
    const eng = r.engine_roster_id ? ` · engine ${esc(r.engine_roster_id)}` : '';
    const roster = r.roster_id ? `car ${esc(r.roster_id)}` : '';
    const meta = [roster, r.engine_roster_id ? `engine ${r.engine_roster_id}` : '', r.engine_model ? `model ${r.engine_model}` : ''].filter(Boolean).join(' · ');
    return `
    <article class="card${ch}" data-src="${esc(r.source_image)}">
      <div class="card-head">
        <div class="title">HART<br>Equipment Card</div>
        <div class="badge">FORM 101-A<br>REV 2026</div>
      </div>
      <div class="card-photo">${img}</div>
      <div class="card-fields">
        <div class="field"><label>Type</label>
          <select data-k="car_type">${options(carTypes, r.car_type)}</select></div>
        <div class="field"><label>Road name</label>
          <select data-k="road_name">${options(roadNames, r.road_name)}</select></div>
        <div class="field"><label>Road #</label>
          <input data-k="road_number" value="${esc(r.road_number)}"></div>
        <div class="field"><label>Description</label>
          <textarea data-k="description">${esc(r.description)}</textarea></div>
      </div>
      <div class="meta">${esc(r.source_image)}${meta ? ' · ' + esc(meta) : ''}</div>
    </article>`;
  }).join('');

  grid.querySelectorAll('.card select, .card input, .card textarea').forEach(el => {
    el.addEventListener('change', onFieldChange);
    el.addEventListener('input', onFieldChange);
  });
  grid.querySelectorAll('.card-photo img').forEach(img => {
    img.addEventListener('click', e => {
      e.stopPropagation();
      const lb = document.getElementById('lightbox');
      lb.querySelector('img').src = img.dataset.full || img.src;
      lb.classList.add('open');
    });
  });
}

function onFieldChange(e) {
  const card = e.target.closest('.card');
  const src = card.dataset.src;
  const row = rows.find(r => r.source_image === src);
  if (!row) return;
  const k = e.target.dataset.k;
  row[k] = e.target.value;
  card.classList.toggle('changed', isChanged(row));
  updateStats();
}

function updateStats() {
  document.getElementById('stats').textContent =
    `${rows.length} cards · ${rows.filter(isChanged).length} changed`;
}

function addLookup(kind, value) {
  value = value.trim();
  if (!value) return;
  const list = kind === 'type' ? carTypes : roadNames;
  if (!list.includes(value)) {
    list.push(value);
    list.sort((a,b) => a.localeCompare(b));
    renderLookupList(kind === 'type' ? 'typeList' : 'roadList', list, kind);
    renderCards();
  }
}

function rebuildDescriptions() {
  rows.forEach(r => {
    const parts = [];
    if (r.is_engine || (r.car_type || '').toLowerCase() === 'locomotive') {
      if (r.manufacturer) parts.push(r.manufacturer);
      if (r.engine_model) parts.push(r.engine_model);
      else if (r.car_type && r.car_type !== 'Locomotive') parts.push(r.car_type);
    } else if ((r.car_type || '').toLowerCase() === 'streetcar') {
      parts.push('PCC');
      parts.push('Streetcar');
    } else {
      if (r.color) parts.push(r.color);
      if (r.car_type) {
        let t = r.car_type;
        if (t.toLowerCase().endsWith('car') && !t.includes(' ')) t = t.slice(0,-3) + ' Car';
        parts.push(t);
      }
    }
    if (r.length_ft) parts.push(r.length_ft + "'");
    r.description = parts.join(' · ');
  });
  renderCards();
  buildExport();
}

function buildExport() {
  const customCarTypes = carTypes.filter(t => !DATA.carTypes.includes(t));
  const customRoadNames = roadNames.filter(r => !DATA.roadNames.includes(r));
  const changes = rows.filter(isChanged).map(r => ({
    source_image: r.source_image,
    car_type: r.car_type,
    reporting_marks: r.road_name,
    road_name: r.road_name,
    road_number: r.road_number,
    description: r.description,
    color: r.color,
    roster_id: r.roster_id,
    engine_roster_id: r.engine_roster_id,
    engine_model: r.engine_model,
  }));
  const payload = {
    version: 1,
    generated_from: 'card_review.html',
    customCarTypes,
    customRoadNames,
    changes,
  };
  document.getElementById('exportBox').value = JSON.stringify(payload, null, 2);
}

document.getElementById('filter').addEventListener('input', renderCards);
document.getElementById('changedOnly').addEventListener('change', renderCards);
document.getElementById('btnRebuildDesc').addEventListener('click', rebuildDescriptions);
document.getElementById('btnExport').addEventListener('click', buildExport);
document.getElementById('btnCopy').addEventListener('click', async () => {
  buildExport();
  const t = document.getElementById('exportBox');
  t.select();
  try { await navigator.clipboard.writeText(t.value); } catch (_) {}
});
document.getElementById('addType').addEventListener('click', () => addLookup('type', document.getElementById('newType').value));
document.getElementById('addRoad').addEventListener('click', () => addLookup('road', document.getElementById('newRoad').value));
document.getElementById('typeList').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  const v = e.target.dataset.value;
  carTypes = carTypes.filter(x => x !== v);
  renderLookupList('typeList', carTypes, 'type');
});
document.getElementById('roadList').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  const v = e.target.dataset.value;
  roadNames = roadNames.filter(x => x !== v);
  renderLookupList('roadList', roadNames, 'road');
});
document.getElementById('lightbox').addEventListener('click', () => {
  document.getElementById('lightbox').classList.remove('open');
});

renderLookupList('typeList', carTypes, 'type');
renderLookupList('roadList', roadNames, 'road');
renderCards();
buildExport();
</script>
</body>
</html>
"""


def main() -> None:
    import argparse

    global IMAGE_DIR, OUTPUT
    parser = argparse.ArgumentParser(description="Generate card_review.html")
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=CARD_FILL_DIR,
        help="Folder for card photo paths in the review UI (default: CarImagesCardFill)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Output HTML path (default: card_review.html)",
    )
    args = parser.parse_args()
    IMAGE_DIR = args.image_dir.resolve()
    OUTPUT = args.output.resolve()

    rows = load_rows()
    car_types, road_names = collect_lookups(rows)
    payload = {
        "carTypes": car_types,
        "roadNames": road_names,
        "rows": rows,
    }
    html = HTML_TEMPLATE.replace("__DATA_JSON__", json.dumps(payload, indent=2))
    OUTPUT.write_text(html, encoding="utf-8")
    engines = sum(1 for r in rows if r["engine_roster_id"])
    print(f"Wrote {OUTPUT}")
    print(f"  {len(rows)} cards · {engines} engine roster matches")


if __name__ == "__main__":
    main()
