#!/usr/bin/env python3
"""Convert Digicon SHSM masts to AAR-1946 and assign Layout Editor facing.

Edits tables/new_tables.xml then copies to jmri/layouts/hart/output/tables.xml.
Also patches hart_prod.xml in place (mast names + facing; not a full copy).

Facing SoR: cats/data/le_signal_boundaries.csv
  turnout ident + A/B/C/D → child <signalAMast>…</signalAMast> (schema, not attributes)
  anchor ident + east/west → eastboundsignalmast / westboundsignalmast attributes

Does not write SignalMastLogic pairs. After facing changes, run
`python3 cats/scripts/apply_sml_cats_pairs.py` (stored occupancy/turnouts).
Do not re-run Discover — it wipes those lists and dests stay inactive.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL = ROOT / "tables/new_tables.xml"
CSV_PATH = ROOT / "cats/data/le_signal_boundaries.csv"
SYNC_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
HART_PROD = ROOT / "jmri/layouts/hart/output/hart_prod.xml"
PREF_TABLES = Path.home() / "Library/Preferences/JMRI/My_JMRI_Railroad.jmri/tables.xml"

TURNOUT_ATTR = {"A": "signalAMast", "B": "signalBMast", "C": "signalCMast", "D": "signalDMast"}
ANCHOR_ATTR = {"east": "eastboundsignalmast", "west": "westboundsignalmast"}

_SHSM_2 = "IF$shsm:cats-masts:cats-virtual-2"
_SHSM_1 = "IF$shsm:cats-masts:cats-virtual-dwarf"
_AAR_2 = "IF$shsm:AAR-1946:SL-2-high-abs"
_AAR_1 = "IF$shsm:AAR-1946:SL-1-low"

_DISABLED_2 = """      <unlit allowed="no" />
      <disabledAspects>
        <disabledAspect>Clear Alt</disabledAspect>
        <disabledAspect>Advance Approach Medium</disabledAspect>
        <disabledAspect>Approach Medium</disabledAspect>
        <disabledAspect>Advance Approach</disabledAspect>
        <disabledAspect>Medium Clear</disabledAspect>
        <disabledAspect>Medium Approach</disabledAspect>
        <disabledAspect>Restricting</disabledAspect>
      </disabledAspects>"""


def load_assignments(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    turnouts: dict[str, dict[str, str]] = {}
    anchors: dict[str, dict[str, str]] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            ident = row["ident"]
            slot = row["slot"]
            mast = row["mast_user_name"]
            if row["kind"] == "turnout":
                turnouts.setdefault(ident, {})[slot] = mast
            elif row["kind"] == "anchor":
                anchors.setdefault(ident, {})[slot] = mast
            else:
                raise SystemExit(f"Unknown kind {row['kind']!r}")
    return turnouts, anchors


def convert_mast_system_names(text: str) -> str:
    text = text.replace(_SHSM_2, _AAR_2)
    text = text.replace(_SHSM_1, _AAR_1)
    return text


def ensure_disabled_restricting(text: str) -> str:
    """Disable Restricting on AAR 2-head SHSM."""

    def repl(m: re.Match[str]) -> str:
        block = m.group(0)
        if "disabledAspects" in block:
            return block
        return block.replace('      <unlit allowed="no" />', _DISABLED_2, 1)

    return re.sub(
        r"    <signalmast class=\"jmri\.implementation\.configurexml\.SignalHeadSignalMastXml\">\s*"
        r"<systemName>IF\$shsm:AAR-1946:SL-2-high-abs\([^<]+\)</systemName>.*?</signalmast>",
        repl,
        text,
        flags=re.S,
    )


def _upsert_attrs(tag: str, attrs: dict[str, str]) -> str:
    self_close = tag.rstrip().endswith("/>")
    inner = tag.strip()
    if inner.startswith("<"):
        inner = inner[1:]
    if inner.endswith("/>"):
        inner = inner[:-2].rstrip()
    elif inner.endswith(">"):
        inner = inner[:-1].rstrip()
    for key, val in attrs.items():
        pat = rf'\s{re.escape(key)}="[^"]*"'
        if re.search(pat, inner):
            inner = re.sub(pat, f' {key}="{val}"', inner, count=1)
        else:
            inner = inner + f' {key}="{val}"'
    return "<" + inner + (" />" if self_close else ">")


_MAST_ATTR_RE = re.compile(r'\s+signal[ABCD]Mast="[^"]*"')


def _strip_turnout_mast_attrs(tag: str) -> str:
    return _MAST_ATTR_RE.sub("", tag)


def apply_facing(text: str, turnouts: dict[str, dict[str, str]], anchors: dict[str, dict[str, str]]) -> str:
    # Schema: signalAMast etc. are child elements, not attributes (cvc-complex-type.3.2.2).
    def turnout_repl(m: re.Match[str]) -> str:
        ident = m.group("ident")
        indent = m.group("indent")
        open_tag = _strip_turnout_mast_attrs(m.group("open"))
        slots = turnouts.get(ident)
        if not slots:
            return f"{indent}<{open_tag} />"
        kids = "".join(
            f"{indent}  <{TURNOUT_ATTR[k]}>{v}</{TURNOUT_ATTR[k]}>\n"
            for k, v in sorted(slots.items())
        )
        return f"{indent}<{open_tag}>\n{kids}{indent}</layoutturnout>"

    text = re.sub(
        r"(?P<indent>[ \t]*)<(?P<open>layoutturnout(?P<body>\s+ident=\"(?P<ident>[^\"]+)\"[^>]*?))\s*/>",
        turnout_repl,
        text,
    )

    def anchor_repl(m: re.Match[str]) -> str:
        ident = m.group("ident")
        slots = anchors.get(ident)
        if not slots:
            return m.group(0)
        attrs = {ANCHOR_ATTR[k]: v for k, v in slots.items()}
        return _upsert_attrs(m.group(0), attrs)

    text = re.sub(
        r"<positionablepoint(?P<body>\s+ident=\"(?P<ident>[^\"]+)\"[^>]*)/>",
        anchor_repl,
        text,
    )
    return text


# JMRI Turnout.CLOSED=2, THROWN=4, UNKNOWN=1. Layout Editor stores
# continuingSense as those constants. continuing="1" is UNKNOWN: both
# legs draw and the frog ignores table Closed/Thrown (114/115 look stuck).
# Closed = continuing (B / through) for 114/115 (CLOSED→K stubs, THROWN→balloon)
# and for 111/113/117 (MQTT CLOSED = through mains).
_CONTINUING_CLOSED = (
    "TOL29",  # 115
    "TOR36",  # 114
    "TO111",
    "TO113",
    "TO117",
)


def fix_princess_continuing(text: str) -> str:
    for ident in _CONTINUING_CLOSED:
        text = re.sub(
            rf'(<layoutturnout\b[^>]*\bident="{ident}"[^>]*\bcontinuing=")[14](")',
            r"\g<1>2\g<2>",
            text,
        )
    return text


def enable_blockrouting(text: str) -> str:
    """SML Discover requires Layout Block advanced routing."""

    def repl(m: re.Match[str]) -> str:
        tag = m.group(0)
        if 'blockrouting="' in tag:
            return re.sub(r'blockrouting="[^"]*"', 'blockrouting="yes"', tag, count=1)
        return tag[:-1] + ' blockrouting="yes">'

    return re.sub(
        r"<layoutblocks class=\"jmri\.jmrit\.display\.layoutEditor\.configurexml\.LayoutBlockManagerXml\"[^>]*>",
        repl,
        text,
        count=1,
    )


def transform(text: str, turnouts: dict, anchors: dict) -> str:
    text = convert_mast_system_names(text)
    text = ensure_disabled_restricting(text)
    text = enable_blockrouting(text)
    text = apply_facing(text, turnouts, anchors)
    text = fix_princess_continuing(text)
    return text


def patch_file(path: Path, turnouts: dict, anchors: dict, *, dry_run: bool) -> None:
    original = path.read_text(encoding="utf-8")
    out = transform(original, turnouts, anchors)
    n2 = out.count(_AAR_2)
    n1 = out.count(_AAR_1)
    n_kids = sum(out.count(f"<{a}>") for a in TURNOUT_ATTR.values())
    n_anchor = sum(out.count(a + "=") for a in ANCHOR_ATTR.values())
    print(f"{path.name}: AAR 2-head={n2} dwarf={n1} turnout-mast-els={n_kids} anchor-attrs={n_anchor}")
    if dry_run:
        return
    path.write_text(out, encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--no-pref", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    turnouts, anchors = load_assignments(args.csv)
    patch_file(args.panel, turnouts, anchors, dry_run=args.dry_run)
    if args.dry_run or args.no_sync:
        return
    shutil.copy2(args.panel, SYNC_TABLES)
    print(f"synced {SYNC_TABLES.relative_to(ROOT)}")
    if HART_PROD.is_file():
        patch_file(HART_PROD, turnouts, anchors, dry_run=False)
    if not args.no_pref and PREF_TABLES.is_file():
        shutil.copy2(args.panel, PREF_TABLES)
        print(f"synced preference {PREF_TABLES}")


if __name__ == "__main__":
    main()
