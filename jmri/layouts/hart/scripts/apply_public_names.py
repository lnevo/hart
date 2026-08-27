#!/usr/bin/env python3
"""Apply ADR-005 public equipment renames from public_name_map.csv.

Default is dry-run. Pass --apply to write files.

Renames userName text and XML fields that store public names (blocks, masts,
heads, turnouts, CTC SIDI/TRL, SML pairs, LayoutEditor bindings). Never touches
systemName values (including ISNX:*), MQTT ids, or CTC IS* internals.
Occupancy Block n-n and FB Switch n-n userNames are separate layers and are
not whole-file replaced (comments keep Block n-n).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

DEFAULT_MAP = Path(__file__).resolve().parents[1] / "data" / "public_name_map.csv"
DEFAULT_TABLES = Path(__file__).resolve().parents[1] / "output" / "tables.xml"

RENAME_LAYERS = frozenset({"block", "mast", "head", "turnout"})
OPTIONAL_MISSING = frozenset(
    {
        "ET-1",
        "ET-2",
        "ET-3",
        "Block 100-102",
        "Yard T1",
        "Yard T6",
        "South Yard Scale",
        "South Yard West",
        "West Yard 1",
        "West Yard 2",
        "South Yard East",
        "Engine House 1",
        "Engine House 2",
        "Engine House 3",
        "MoveToWest_Yard_1_stored",
        "MoveToWest_Yard_2_stored",
        "MoveToSouth_Yard_East_stored",
        "MoveToEngine_House_1_stored",
        "MoveToEngine_House_2_stored",
        "MoveToEngine_House_3_stored",
        "MoveInProgressWest_Yard_1",
        "MoveInProgressWest_Yard_2",
        "MoveInProgressSouth_Yard_East",
        "MoveInProgressEngine_House_1",
        "MoveInProgressEngine_House_2",
        "MoveInProgressEngine_House_3",
    }
)

# Dispatcher MoveTo / MoveInProgress userNames are station.replace(" ","_").
# Plate names (W-1, EH-1) keep the hyphen; spaces become underscores.
DISPATCHER_SENSOR_RENAMES = (
    ("MoveToWest_Yard_1_stored", "MoveToW-1_stored"),
    ("MoveInProgressWest_Yard_1", "MoveInProgressW-1"),
    ("MoveToWest_Yard_2_stored", "MoveToW-2_stored"),
    ("MoveInProgressWest_Yard_2", "MoveInProgressW-2"),
    ("MoveToSouth_Yard_East_stored", "MoveToEast_Lead_stored"),
    ("MoveInProgressSouth_Yard_East", "MoveInProgressEast_Lead"),
    ("MoveToEngine_House_1_stored", "MoveToEH-1_stored"),
    ("MoveInProgressEngine_House_1", "MoveInProgressEH-1"),
    ("MoveToEngine_House_2_stored", "MoveToEH-2_stored"),
    ("MoveInProgressEngine_House_2", "MoveInProgressEH-2"),
    ("MoveToEngine_House_3_stored", "MoveToEH-3_stored"),
    ("MoveInProgressEngine_House_3", "MoveInProgressEH-3"),
)

PUBLIC_NAME_ATTRS = frozenset(
    {
        "blockname",
        "blockcname",
        "blockdname",
        "blockcontents",
        "signalmast",
        "source",
        "destination",
        "userName",
    }
)

PUBLIC_NAME_TAGS = frozenset(
    {
        "userName",
        "sourceSignalMast",
        "destinationSignalMast",
        "associatedSection",
        "DestinationSignalOrComment",
        "signal",
        "signalAMast",
        "signalBMast",
        "signalCMast",
        "signalDMast",
        "tooltip",
        "value",
    }
)

FROZEN_PREFIX_RE = re.compile(r"^(M2T|M2S|IH|IF\$shsm|IS:|ISNX:)")
SENSOR_BLOCK_USERNAME_RE = re.compile(r"^Block \d+-\d+$")
# Protect hardware ids in whole-file replace so 100L inside ISNX:100L is untouched.
_PROTECT_RE = re.compile(
    r"(<systemName>[^<]*</systemName>"
    r"|systemName=\"[^\"]*\""
    r"|ISNX:[A-Za-z0-9:._-]+"
    r"|IF\$shsm:[^<\s\"]+"
    r"|M2[TS]\d+|IH\d+)",
    re.I,
)


@dataclass(frozen=True)
class RenameEntry:
    layer: str
    current: str
    proposed: str
    optional: bool = False


def load_rename_map(csv_path: Path | str) -> list[RenameEntry]:
    """Load rename rows where current != proposed, longest current names first."""
    path = Path(csv_path)
    entries: list[RenameEntry] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            layer = (row.get("layer") or "").strip()
            current = (row.get("current") or "").strip()
            proposed = (row.get("proposed") or "").strip()
            if layer not in RENAME_LAYERS or not current or current == proposed:
                continue
            notes = (row.get("notes") or "").strip().lower()
            optional = current in OPTIONAL_MISSING or notes.startswith("historical alias")
            entries.append(
                RenameEntry(
                    layer=layer,
                    current=current,
                    proposed=proposed,
                    optional=optional,
                )
            )
    for current, proposed in DISPATCHER_SENSOR_RENAMES:
        if current != proposed:
            entries.append(
                RenameEntry(
                    layer="sensor",
                    current=current,
                    proposed=proposed,
                    optional=True,
                )
            )
    entries.sort(key=lambda item: len(item.current), reverse=True)
    return entries


def _is_frozen_public_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if SENSOR_BLOCK_USERNAME_RE.fullmatch(stripped):
        return True
    return bool(FROZEN_PREFIX_RE.match(stripped))


def _protect_frozen_tokens(text: str) -> tuple[str, list[str]]:
    stashed: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        stashed.append(match.group(0))
        return f"__HART_PROTECT_{len(stashed) - 1}__"

    return _PROTECT_RE.sub(_stash, text), stashed


def _restore_frozen_tokens(text: str, stashed: list[str]) -> str:
    restored = text
    for index, original in enumerate(stashed):
        restored = restored.replace(f"__HART_PROTECT_{index}__", original)
    return restored


def _replace_in_string(text: str, renames: list[RenameEntry], counts: Counter[tuple[str, str]]) -> str:
    """Two-phase replace so S-2→OS S-1 cannot then become OS S-R."""
    if not text:
        return text
    work, stashed = _protect_frozen_tokens(text)
    tokens: list[tuple[str, RenameEntry]] = []
    for index, entry in enumerate(renames):
        token = f"__HART_RN_{index}__"
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(entry.current) + r"(?![A-Za-z0-9])"
        )
        work, n = pattern.subn(token, work)
        if n:
            counts[(entry.current, entry.proposed)] += n
            tokens.append((token, entry))
    for token, entry in tokens:
        work = work.replace(token, entry.proposed)
    return _restore_frozen_tokens(work, stashed)


def _should_replace_element_text(elem: ET.Element, parent: ET.Element | None) -> bool:
    if elem.tag == "systemName":
        return False
    if elem.tag == "userName" and parent is not None:
        if parent.tag == "sensor":
            text = (elem.text or "").strip()
            if SENSOR_BLOCK_USERNAME_RE.fullmatch(text):
                return False
    text = elem.text or ""
    if _is_frozen_public_text(text):
        return False
    return elem.tag in PUBLIC_NAME_TAGS


def _should_replace_attr_value(attr_name: str, value: str) -> bool:
    if attr_name == "systemName":
        return False
    if attr_name not in PUBLIC_NAME_ATTRS:
        return False
    return not _is_frozen_public_text(value)


def apply_renames_to_tree(root: ET.Element, renames: list[RenameEntry]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    parent_map: dict[int, ET.Element] = {}
    for parent in root.iter():
        for child in list(parent):
            parent_map[id(child)] = parent

    for elem in root.iter():
        parent = parent_map.get(id(elem))
        if _should_replace_element_text(elem, parent) and elem.text:
            new_text = _replace_in_string(elem.text, renames, counts)
            if new_text != elem.text:
                elem.text = new_text

        for attr_name, attr_value in list(elem.attrib.items()):
            if not attr_value or not _should_replace_attr_value(attr_name, attr_value):
                continue
            new_value = _replace_in_string(attr_value, renames, counts)
            if new_value != attr_value:
                elem.set(attr_name, new_value)

    return counts


def collect_system_names(root: ET.Element) -> list[str]:
    names: list[str] = []
    for elem in root.iter():
        if elem.tag == "systemName" and elem.text:
            names.append(elem.text)
        system_name_attr = elem.get("systemName")
        if system_name_attr:
            names.append(system_name_attr)
    return names


def find_missing_current_names(content: str, renames: list[RenameEntry]) -> list[str]:
    missing: list[str] = []
    for entry in renames:
        if entry.optional or entry.current in OPTIONAL_MISSING:
            continue
        if entry.current not in content:
            missing.append(entry.current)
    return missing


def apply_renames_to_text(content: str, renames: list[RenameEntry]) -> tuple[str, Counter[tuple[str, str]]]:
    """Longest-first exact string replace. Preserves XML/text formatting."""
    counts: Counter[tuple[str, str]] = Counter()
    updated = _replace_in_string(content, renames, counts)
    return updated, counts


def load_sensor_username_map(csv_path: Path | str) -> dict[str, str]:
    """occupancy + fb layers: sensor userName only (comments stay Block n-n)."""
    path = Path(csv_path)
    mapping: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            layer = (row.get("layer") or "").strip()
            if layer not in {"occupancy", "fb"}:
                continue
            current = (row.get("current") or "").strip()
            proposed = (row.get("proposed") or "").strip()
            if current and proposed and current != proposed:
                mapping[current] = proposed
    return mapping


def apply_sensor_usernames_to_text(
    content: str, mapping: dict[str, str]
) -> tuple[str, int]:
    if not mapping:
        return content, 0
    hits = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal hits
        name = match.group(1)
        new = mapping.get(name)
        if not new:
            return match.group(0)
        hits += 1
        return f"<userName>{new}</userName>"

    updated = re.sub(r"<userName>([^<]*)</userName>", repl, content)
    return updated, hits


def apply_renames_to_xml_file(
    xml_path: Path | str,
    renames: list[RenameEntry],
    *,
    apply: bool = False,
    sensor_usernames: dict[str, str] | None = None,
) -> tuple[Counter[tuple[str, str]], bool]:
    """Apply renames to one XML file. Returns replacement counts and systemName_ok."""
    path = Path(xml_path)
    original = path.read_text(encoding="utf-8")
    before_system_names = collect_system_names(ET.fromstring(original))
    updated, counts = apply_renames_to_text(original, renames)
    if sensor_usernames:
        updated, sensor_n = apply_sensor_usernames_to_text(updated, sensor_usernames)
        if sensor_n:
            counts[("(sensor userName)", f"{sensor_n} occupancy/fb")] += sensor_n
    after_system_names = collect_system_names(ET.fromstring(updated))
    system_names_ok = before_system_names == after_system_names

    if apply and system_names_ok and updated != original:
        path.write_text(updated, encoding="utf-8")

    return counts, system_names_ok


def apply_public_names(
    xml_path: Path | str,
    renames: list[RenameEntry],
    *,
    apply: bool = False,
    sensor_usernames: dict[str, str] | None = None,
) -> tuple[Counter[tuple[str, str]], list[str], bool]:
    """Apply renames after verifying all required current names exist in the file."""
    path = Path(xml_path)
    original = path.read_text(encoding="utf-8")
    missing = find_missing_current_names(original, renames)
    counts, system_names_ok = apply_renames_to_xml_file(
        path, renames, apply=apply, sensor_usernames=sensor_usernames
    )
    return counts, missing, system_names_ok


def merge_counts(counts_list: list[Counter[tuple[str, str]]]) -> Counter[tuple[str, str]]:
    merged: Counter[tuple[str, str]] = Counter()
    for counts in counts_list:
        merged.update(counts)
    return merged


def print_summary(counts: Counter[tuple[str, str]], *, dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "APPLIED"
    print(f"\n{mode} replacement summary:")
    print(f"{'old':<40} {'new':<40} {'count':>6}")
    print("-" * 90)
    total = 0
    for (old, new), count in sorted(counts.items(), key=lambda item: (-item[1], item[0][0])):
        print(f"{old:<40} {new:<40} {count:>6}")
        total += count
    print("-" * 90)
    print(f"{'TOTAL':<81} {total:>6}")
    if total == 0:
        print("(no replacements)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--map",
        type=Path,
        default=DEFAULT_MAP,
        help=f"Rename CSV (default: {DEFAULT_MAP})",
    )
    parser.add_argument(
        "--tables",
        type=Path,
        default=DEFAULT_TABLES,
        help=f"Primary tables.xml path (default: {DEFAULT_TABLES})",
    )
    parser.add_argument(
        "--also",
        type=Path,
        action="append",
        default=[],
        help="Additional XML paths to process (e.g. hart_prod.xml)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to disk (default is dry-run)",
    )
    args = parser.parse_args(argv)

    renames = load_rename_map(args.map)
    sensor_usernames = load_sensor_username_map(args.map)
    targets = [args.tables, *args.also]

    all_counts: list[Counter[tuple[str, str]]] = []
    missing_names: list[str] = []
    system_names_ok = True

    for target in targets:
        if not target.is_file():
            print(f"error: file not found: {target}", file=sys.stderr)
            return 1
        counts, missing, names_ok = apply_public_names(
            target,
            renames,
            apply=args.apply,
            sensor_usernames=sensor_usernames,
        )
        all_counts.append(counts)
        missing_names.extend(missing)
        system_names_ok = system_names_ok and names_ok

    merged = merge_counts(all_counts)
    print_summary(merged, dry_run=not args.apply)

    if missing_names:
        unique_missing = sorted(set(missing_names))
        print("\nNames not present in every file (ok if that file never had them):")
        for name in unique_missing:
            print(f"  - {name}")

    if not system_names_ok:
        print("\nerror: a replacement would change a systemName", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
