#!/usr/bin/env python3
"""Assign Layout Editor facing. Does not change mast types.

Edits jmri/layouts/hart/output/tables.xml. Its main panel must be the generated one (build_layout_le.py --as-live):
each mast goes in its row's slot. Any other panel is refused, and only the checkout's own tables.xml is copied to
the JMRI profile.


Facing SoR: jmri/layouts/hart/data/le_signal_boundaries.csv
  turnout ident + A/B/C/D → child <signalAMast>…</signalAMast> (schema, not attributes)
  anchor ident + east/west → eastboundsignalmast / westboundsignalmast attributes

Does not write SignalMastLogic pairs. SML dests are native (Layout Editor Discover,
useLayoutEditor=yes). After facing changes, re-run Discover with
`jmri/layouts/hart/scripts/run_sml_discover.sh`, which then sets the Digicon dests to
Enabled=no. Check the result by comparing the stored pairs with the previous tables
(`data/baselines/sml_pairs.csv`).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import boundaries, paths, tables  # noqa: E402

DEFAULT_PANEL = paths.TABLES_XML
CSV_PATH = boundaries.PATH
PREF_TABLES = paths.JMRI_USER_FILES / "tables.xml"

TURNOUT_ATTR = {"A": "signalAMast", "B": "signalBMast", "C": "signalCMast", "D": "signalDMast"}
ANCHOR_ATTR = {"east": "eastboundsignalmast", "west": "westboundsignalmast"}

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
    """({turnout ident: {slot: mast}}, {anchor ident: {slot: mast}}) from the boundaries CSV, each row in its slot on
    the generated panel."""
    turnouts: dict[str, dict[str, str]] = {}
    anchors: dict[str, dict[str, str]] = {}
    try:
        rows = boundaries.read(path)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    for b in rows:
        (turnouts if b.kind == "turnout" else anchors).setdefault(b.ident, {})[b.slot] = b.mast
    return turnouts, anchors


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
    if not args.dry_run:
        paths.exit_if_overridden(Path(__file__).name)
    syncing = not (args.dry_run or args.no_sync or args.no_pref) and PREF_TABLES.is_file()
    try:
        tables.require_generated_panel(tables.read(args.panel), str(args.panel))
    except (OSError, ET.ParseError) as exc:
        print(f"{args.panel}: cannot read it: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    # Only the checkout's own tables.xml reaches the profile: a cut-over candidate or sandbox copy named by --panel is
    # never copied there.
    if syncing and Path(os.path.realpath(args.panel)) != Path(os.path.realpath(paths.REPO_TABLES_XML)):
        print(f"{args.panel}: not the checkout's tables.xml, so it is not copied to {PREF_TABLES}; rerun with "
              "--no-pref (or --no-sync)", file=sys.stderr)
        sys.exit(1)
    turnouts, anchors = load_assignments(args.csv)
    patch_file(args.panel, turnouts, anchors, dry_run=args.dry_run)
    if args.dry_run or args.no_sync:
        return
    if syncing:
        shutil.copy2(args.panel, PREF_TABLES)
        print(f"synced preference {PREF_TABLES}")


if __name__ == "__main__":
    main()
