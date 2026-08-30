#!/usr/bin/env python3
"""Rebuild public_name_map.csv from the HART Device map + live tables.

After a convert, identity rows must be current == proposed == live userName.
Device-map comments land in the `comment` column. Historical aliases stay so
leftover strings still convert.

Default is dry-run. Pass --write-csv / --apply-comments to write.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_bean_comments import public_comment

CSV_PATH = ROOT / "jmri/layouts/hart/data/public_name_map.csv"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
NEW_TABLES = ROOT / "tables/new_tables.xml"
HART_PROD = ROOT / "jmri/layouts/hart/output/hart_prod.xml"
DEFAULT_CANVAS = Path.home() / ".cursor/projects/Users-lnevo-hart/canvases/hart-device-map.canvas.tsx"

KIND_LAYER = {
    "Turnout": "turnout",
    "LCC turnout": "turnout",
    "Occupancy": "occupancy",
    "Occupancy (unused)": "occupancy",
    "OS block": "block",
    "Block": "block",
    "Feedback": "fb",
    "Feedback (unused)": "fb",
    "Signal head": "head",
    "Signal mast": "mast",
    "Virtual mast": "mast",
}

LAYER_ORDER = ("turnout", "block", "occupancy", "mast", "head", "fb")

BEAN_RE = re.compile(
    r"(<(sensor|turnout|block|signalhead|signalmast|virtualsignalmast)\b[^>]*>)(.*?)(</\2>)",
    re.S,
)

PROTECTED_COMMENT_RE = re.compile(
    r"(?:unused LCOS|\bstop\b|not a station)",
    re.I,
)

DEVICES_RE = re.compile(
    r"const DEVICES: Device\[\] = \[(.*?)\];",
    re.S,
)


def child_text(body: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", body, re.S)
    return match.group(1).strip() if match else ""


def set_comment(body: str, comment: str) -> str:
    escaped = (
        comment.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    if re.search(r"<comment>.*?</comment>", body, re.S):
        return re.sub(
            r"<comment>.*?</comment>",
            f"<comment>{escaped}</comment>",
            body,
            count=1,
            flags=re.S,
        )
    insert = f"\n      <comment>{escaped}</comment>"
    for tag in ("userName", "systemName"):
        match = re.search(rf"</{tag}>", body)
        if match:
            return body[: match.end()] + insert + body[match.end() :]
    return body.rstrip() + insert + "\n    "


def rewrite_canvas_comments(path: Path, devices: list[dict[str, str]]) -> int:
    text = path.read_text(encoding="utf-8")
    changed = 0
    for device in devices:
        new_comment = public_comment(device["kind"], device["userName"], device["comment"])
        if new_comment == device["comment"]:
            continue
        old = json.dumps(device, separators=(",", ":"))
        updated = dict(device)
        updated["comment"] = new_comment
        new = json.dumps(updated, separators=(",", ":"))
        if old not in text:
            raise SystemExit(f"{path}: missing device {device['userName']}")
        text = text.replace(old, new, 1)
        changed += 1
        device["comment"] = new_comment
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def parse_canvas(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    match = DEVICES_RE.search(text)
    if not match:
        raise SystemExit(f"{path}: no DEVICES array")
    devices: list[dict[str, str]] = []
    for raw in re.finditer(r"\{[^{}]+\}", match.group(1)):
        obj = json.loads(raw.group(0))
        devices.append({key: str(value or "") for key, value in obj.items()})
    if not devices:
        raise SystemExit(f"{path}: empty DEVICES array")
    return devices


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = []
        for row in csv.DictReader(handle):
            rows.append({key: (value or "").strip() for key, value in row.items() if key})
        return rows


def live_usernames_by_system(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    out: dict[str, str] = {}

    def take(tag: str) -> None:
        for el in root.iter(tag):
            system_name = (el.findtext("systemName") or el.get("systemName") or "").strip()
            user_name = (el.findtext("userName") or "").strip()
            if system_name and user_name:
                # Prefer the full block (has occupancysensor) over the stub.
                if tag == "block" and system_name in out and el.find("occupancysensor") is None:
                    continue
                out[system_name] = user_name

    for tag in (
        "sensor",
        "turnout",
        "block",
        "signalhead",
        "signalmast",
        "virtualsignalmast",
    ):
        take(tag)
    return out


def hardware_for(device: dict[str, str], old_by_proposed: dict[tuple[str, str], dict[str, str]]) -> str:
    layer = KIND_LAYER[device["kind"]]
    system_name = device["systemName"].strip()
    user_name = device["userName"].strip()
    old = old_by_proposed.get((layer, user_name))
    if old and old.get("hardware"):
        return old["hardware"]
    if system_name.startswith(("M2T", "M2S", "IH", "MTT")):
        return system_name
    if device["comment"].startswith("Block "):
        return device["comment"]
    return system_name


def cp_for(device: dict[str, str], old_by_proposed: dict[tuple[str, str], dict[str, str]]) -> str:
    layer = KIND_LAYER[device["kind"]]
    user_name = device["userName"].strip()
    kind = device["kind"]
    if kind in {"OS block", "Block", "Signal mast", "Virtual mast"}:
        return device["comment"].strip().split("|")[0].strip()
    old = old_by_proposed.get((layer, user_name))
    if old:
        return old.get("cp") or ""
    return ""


def rebuild_rows(
    devices: list[dict[str, str]],
    old_rows: list[dict[str, str]],
    live: dict[str, str],
) -> list[dict[str, str]]:
    old_by_proposed: dict[tuple[str, str], dict[str, str]] = {}
    for row in old_rows:
        notes = (row.get("notes") or "").lower()
        if "historical alias" in notes:
            continue
        key = (row["layer"], row["proposed"])
        old_by_proposed.setdefault(key, row)

    identity: dict[tuple[str, str], dict[str, str]] = {}
    for device in devices:
        kind = device["kind"]
        if kind not in KIND_LAYER:
            continue
        layer = KIND_LAYER[kind]
        system_name = device["systemName"].strip()
        if system_name and system_name not in live:
            continue
        live_name = live.get(system_name) or device["userName"].strip()
        if not live_name:
            continue
        row = {
            "layer": layer,
            "current": live_name,
            "proposed": live_name,
            "cp": cp_for({**device, "userName": live_name}, old_by_proposed),
            "hardware": hardware_for({**device, "userName": live_name}, old_by_proposed),
            "comment": public_comment(device["kind"], live_name, device["comment"].strip()),
            "notes": "",
        }
        key = (layer, live_name)
        prev = identity.get(key)
        if prev and prev["comment"] and row["comment"] and prev["comment"] != row["comment"]:
            # Two canvas rows share a live userName (unused occupancy). Keep
            # hardware-specific comments on the first; skip the duplicate key.
            continue
        if prev is None or (not prev["comment"] and row["comment"]):
            identity[key] = row

    alias_rows: list[dict[str, str]] = []
    seen = set(identity)
    for row in old_rows:
        layer = row["layer"]
        current = row["current"]
        proposed = row["proposed"]
        if layer == "fb_comment":
            continue
        if (layer, current) in seen:
            continue
        ident = identity.get((layer, proposed))
        notes = row.get("notes") or ""
        if current != proposed and "historical alias" not in notes.lower():
            notes = f"historical alias; {notes}".strip("; ")
        alias_rows.append(
            {
                "layer": layer,
                "current": current,
                "proposed": ident["proposed"] if ident else proposed,
                "cp": ident["cp"] if ident else row.get("cp") or "",
                "hardware": ident["hardware"] if ident else row.get("hardware") or "",
                "comment": ident["comment"]
                if ident
                else public_comment(layer, proposed, row.get("comment") or ""),
                "notes": notes,
            }
        )
        seen.add((layer, current))

    def sort_key(row: dict[str, str]) -> tuple:
        try:
            layer_i = LAYER_ORDER.index(row["layer"])
        except ValueError:
            layer_i = 99
        identity_i = 0 if row["current"] == row["proposed"] else 1
        return (layer_i, identity_i, row["proposed"], row["current"])

    return sorted(list(identity.values()) + alias_rows, key=sort_key)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["layer", "current", "proposed", "cp", "hardware", "comment", "notes"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def comment_index(rows: list[dict[str, str]]) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """systemName -> comment, and (xml-kind, userName) -> comment for identity rows."""
    by_sys: dict[str, str] = {}
    by_user: dict[tuple[str, str], str] = {}
    layer_kind = {
        "turnout": "turnout",
        "occupancy": "sensor",
        "fb": "sensor",
        "head": "signalhead",
        "mast": "signalmast",
        "block": "block",
    }
    for row in rows:
        if row["current"] != row["proposed"]:
            continue
        comment = (row.get("comment") or "").strip()
        if not comment:
            continue
        hardware = row.get("hardware") or ""
        for token in hardware.split():
            if token.startswith(("M2T", "M2S", "IH", "MTT")):
                by_sys[token] = comment
        xml_kind = layer_kind.get(row["layer"])
        if xml_kind:
            by_user[(xml_kind, row["proposed"])] = comment
            if xml_kind == "signalmast":
                by_user[("virtualsignalmast", row["proposed"])] = comment
    return by_sys, by_user


def apply_comments_to_text(text: str, by_sys: dict[str, str], by_user: dict[tuple[str, str], str]) -> tuple[str, int]:
    changed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        open_tag, kind, body, close_tag = match.group(1), match.group(2), match.group(3), match.group(4)
        system_name = child_text(body, "systemName")
        user_name = child_text(body, "userName")
        existing = child_text(body, "comment")
        if PROTECTED_COMMENT_RE.search(existing):
            return match.group(0)
        if kind == "block" and "<occupancysensor>" not in body:
            return match.group(0)
        comment = by_sys.get(system_name) or by_user.get((kind, user_name))
        if not comment or comment == existing:
            return match.group(0)
        changed += 1
        return open_tag + set_comment(body, comment) + close_tag

    return BEAN_RE.sub(repl, text), changed


def apply_comments(paths: list[Path], rows: list[dict[str, str]], write: bool) -> dict[str, int]:
    by_sys, by_user = comment_index(rows)
    counts: dict[str, int] = {}
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        updated, n = apply_comments_to_text(text, by_sys, by_user)
        counts[str(path.relative_to(ROOT))] = n
        if write and n:
            path.write_text(updated, encoding="utf-8")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canvas", type=Path, default=DEFAULT_CANVAS)
    parser.add_argument("--write-csv", action="store_true")
    parser.add_argument("--write-canvas", action="store_true")
    parser.add_argument("--apply-comments", action="store_true")
    args = parser.parse_args()
    if not args.canvas.is_file():
        print(f"missing Device map canvas: {args.canvas}", file=sys.stderr)
        return 2

    devices = parse_canvas(args.canvas)
    if args.write_canvas:
        n_canvas = rewrite_canvas_comments(args.canvas, devices)
        print(f"canvas comments={n_canvas}")
    else:
        print("canvas dry-run (pass --write-canvas)")

    old_rows = load_csv(CSV_PATH)
    live = live_usernames_by_system(TABLES)
    rows = rebuild_rows(devices, old_rows, live)

    identity = [row for row in rows if row["current"] == row["proposed"]]
    aliases = [row for row in rows if row["current"] != row["proposed"]]
    commented = [row for row in identity if row.get("comment")]
    print(
        f"rows={len(rows)} identity={len(identity)} aliases={len(aliases)} "
        f"identity_with_comment={len(commented)} canvas_devices={len(devices)}"
    )

    if args.write_csv:
        write_csv(CSV_PATH, rows)
        print(f"wrote {CSV_PATH.relative_to(ROOT)}")
    else:
        print("CSV dry-run (pass --write-csv)")

    counts = apply_comments(
        [TABLES, NEW_TABLES, HART_PROD],
        rows,
        write=args.apply_comments,
    )
    for rel, n in counts.items():
        print(f"{rel}: comments={n}{' (written)' if args.apply_comments else ' (dry-run)'}")
    if not args.apply_comments:
        print("comment dry-run (pass --apply-comments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
