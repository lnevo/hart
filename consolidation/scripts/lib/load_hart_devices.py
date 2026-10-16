"""Load HART device map rows (canvas format) for consolidation review HTML."""
from __future__ import annotations

import csv
import json
from pathlib import Path

CON = Path(__file__).resolve().parents[2]
CANVAS_CANDIDATES = [
    Path.home() / ".cursor/projects/Users-lnevo-hart/canvases/hart-device-map.canvas.tsx",
    CON / "sor/names/hart-device-map.canvas.tsx",
]
JSON_SNAPSHOT = CON / "sor/names/hart_devices_review.json"
MERGED_MAP = CON / "sor/names/public_name_map_merged.csv"
LEGACY_CSV = CON / "sor/names/d2_legacy_match.csv"


def load_legacy_rows() -> list[dict[str, str]]:
    """Merged-map rows with D2 notes — for legacy / alias matching only."""
    if not MERGED_MAP.is_file():
        return []
    rows: list[dict[str, str]] = []
    with MERGED_MAP.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            notes = (row.get("notes") or "").strip()
            if not notes:
                continue
            rows.append(
                {
                    "layer": (row.get("layer") or "").strip(),
                    "current": (row.get("current") or "").strip(),
                    "proposed": (row.get("proposed") or "").strip(),
                    "cp": (row.get("cp") or "").strip(),
                    "hardware": (row.get("hardware") or "").strip(),
                    "comment": (row.get("comment") or "").strip(),
                    "notes": notes,
                }
            )
    return rows


def export_legacy_csv(rows: list[dict[str, str]]) -> Path:
    LEGACY_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["layer", "hardware", "current", "proposed", "cp", "comment", "notes"]
    with LEGACY_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    return LEGACY_CSV


def _parse_canvas(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    start = text.index("const DEVICES: Device[] = [")
    end = text.index("];", start)
    devices: list[dict[str, str]] = []
    for line in text[start:end].splitlines():
        s = line.strip().rstrip(",")
        if s.startswith("{"):
            devices.append(json.loads(s))
    return devices


def _notes_by_key() -> dict[str, str]:
    out: dict[str, str] = {}
    if not MERGED_MAP.is_file():
        return out
    with MERGED_MAP.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            notes = (row.get("notes") or "").strip()
            if not notes:
                continue
            hw = (row.get("hardware") or "").strip()
            if hw:
                out[hw] = notes
    return out


def load_devices(*, attach_d2_notes: bool = False) -> tuple[list[dict[str, str]], str]:
    """Return (devices, source_label). Main review omits D2 notes — see d2_legacy_match.csv."""
    for canvas in CANVAS_CANDIDATES:
        if canvas.is_file():
            devices = _parse_canvas(canvas)
            for d in devices:
                d.pop("notes", None)
            if attach_d2_notes:
                _attach_notes(devices)
            return devices, f"hart-device-map.canvas.tsx ({canvas.name})"
    if JSON_SNAPSHOT.is_file():
        devices = json.loads(JSON_SNAPSHOT.read_text(encoding="utf-8"))
        for d in devices:
            d.pop("notes", None)
        if attach_d2_notes:
            _attach_notes(devices)
        return devices, "hart_devices_review.json"
    raise FileNotFoundError(
        "No device map source. Expected canvas at "
        + " or ".join(str(p) for p in CANVAS_CANDIDATES)
        + f" or snapshot {JSON_SNAPSHOT}"
    )


def _attach_notes(devices: list[dict[str, str]]) -> None:
    notes = _notes_by_key()
    for d in devices:
        d["notes"] = notes.get(d.get("systemName", ""), "")


def save_snapshot(devices: list[dict[str, str]]) -> Path:
    JSON_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    JSON_SNAPSHOT.write_text(json.dumps(devices, indent=2), encoding="utf-8")
    return JSON_SNAPSHOT


def count_kind(devices: list[dict], prefix: str) -> int:
    return sum(1 for d in devices if d["kind"].startswith(prefix))


GRAMMAR_ROWS = [
    ["Turnout", "04:8", "100", "408", "M2T408", "Switch 1", "Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2"],
    ["LCC turnout", "—", "100", "—", "MTT100", "DCC Switch 1", "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2"],
    ["Occupancy", "04:00", "—", "400", "M2S400", "BS Switch 3", "Node: 4 Block: 1"],
    ["OS block", "04:00", "—", "400", "IB:AUTO:0035", "OS 3", "Brick"],
    ["Block", "02:07", "—", "207", "IB:AUTO:0012", "OS S-R", "South Yard"],
    ["Feedback", "01:67", "—", "167", "M2S167", "FB Switch 35 N", "Node: 1 Sensor: 0 | IN: 1 Ports: 1"],
    ["Feedback", "04:70", "—", "470", "M2S470", "FB Switch 1 N", "Node: 4 Sensor: 3 | IN: 1 Ports: 1"],
    ["Signal head", "04:38", "—", "438", "IH438", "Head 2L Top", "Node: 4 Signal: 6 | OU: 3 Ports: 1,2,3"],
    ["Signal mast", "—", "—", "—", "IF$shsm:…(IH438)(IH439)", "Mast 2L", "Brick"],
]

KIND_OPTIONS = [
    ("all", "All devices"),
    ("Turnout", "Turnouts"),
    ("LCC turnout", "LCC / DCC turnouts"),
    ("Occupancy", "Occupancy sensors"),
    ("OS block", "OS blocks"),
    ("Block", "Track blocks"),
    ("Feedback", "Feedback sensors"),
    ("Signal head", "Signal heads"),
    ("Signal mast", "Signal masts"),
    ("Virtual mast", "Virtual masts"),
]
