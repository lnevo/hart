#!/usr/bin/env python3
"""Signal heads in tables.xml must follow the wiring plan.

The IH number of a head is its MQTT topic (track/signalhead/<packed>), and the
wiring rule is packed = cabinet radio address x 100 + slot
(docs/wiring/README.md). jmri/layouts/hart/data/wiring.csv holds every wired
head (hartlib.wiring.digicon_rows gives its pins, IH number and mast). This check fails when:

- a physical mast (a SignalHeadSignalMast with a head in wiring.csv) carries
  a head other than its planned head, in planned order (top, bottom);
- a SignalHeadSignalMast in tables.xml is not in the wiring plan;
- a wired mast is missing from tables.xml;
- a wired head is not defined, or is on no mast;
- a wired head's comment disagrees with its node, signal and port list;
- a wiring row's system_name, packed (node x 100 + uid) and topic disagree.

Hidden virtual masts (IF$vsm) carry no wiring and are not checked. The main and upper levels' masts stand on
virtual heads named from their user names (IH:HART:C3:108R_Top; hartlib.level_masts) while their plant is a draft:
they are not in the wiring plan yet, so each must carry exactly the heads masts.csv gives it, and no wired
head is theirs.
Staging's masts stand on internal heads too (IH:HART:C1:24RA_Top; ADR-024), all but Mast 6LB, the one wired mast
(IH432, one high head): each must carry the heads masts.csv gives it. The wiring plan lists wired heads only;
the rest is planned when the owner wires them.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import level_masts, paths, tables, wiring  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402

ROLE_ORDER = {"T": 0, "S": 0, "B": 1}
SHSM_RE = re.compile(r"^IF\$shsm:[^:]+:[^(]+((?:\(IH\d+\))+)$")


class WiringError(ValueError):
    """The wired heads contradict themselves."""


def row_problems(r: dict[str, str]) -> list[str]:
    """A wiring row's IH number, packed number, node, UID and topic must agree."""
    port = (r.get("port_id") or "?").strip()
    name = (r.get("system_name") or "").strip()
    packed = (r.get("packed") or "").strip()
    node = (r.get("mqtt_node") or "").strip()
    uid = (r.get("uid") or "").strip()
    topic = (r.get("topic") or "").strip()
    out: list[str] = []
    if not (r.get("mast_user_name") or "").strip():
        out.append(f"{port}: no mast_user_name")
    if (r.get("head_role") or "").strip() not in ROLE_ORDER:
        out.append(f"{port}: head_role {r.get('head_role')!r} is not T, B or S")
    if name != f"IH{packed}":
        out.append(f"{port}: system_name {name} but packed {packed}")
    if node.isdigit() and uid.isdigit() and packed.isdigit():
        if int(packed) != int(node) * 100 + int(uid):
            out.append(f"{port}: packed {packed} is not node {node} x 100 + uid {uid}")
    else:
        out.append(f"{port}: node {node!r}, uid {uid!r}, packed {packed!r} must be numbers")
    if "topic" in r and topic != f"track/signalhead/{packed}":
        out.append(f"{port}: topic {topic} but packed {packed}")
    return out


def load_wiring(rows: list[dict[str, str]]) -> dict[str, dict]:
    """Wired head system name -> mast, role, comment parts."""
    bad = [p for r in rows for p in row_problems(r)]
    if bad:
        raise WiringError("; ".join(bad))
    heads: dict[str, dict] = {}
    for r in rows:
        name = r["system_name"].strip()
        h = heads.setdefault(
            name,
            {
                "mast": r["mast_user_name"].strip(),
                "role": r["head_role"].strip(),
                "node": r["mqtt_node"].strip(),
                "signals": set(),
                "ports": [],
            },
        )
        if h["mast"] != r["mast_user_name"].strip():
            raise WiringError(f"{name} is wired to two masts")
        h["signals"].add(r["signal_index"].strip())
        h["ports"].append(r["port_id"].strip())
    return heads


def expected_comment(head: dict) -> str:
    groups: list[tuple[str, list[str]]] = []
    for port_id in head["ports"]:
        _cab, ou, port = port_id.split("-")
        ou = ou.removeprefix("OU")
        if groups and groups[-1][0] == ou:
            groups[-1][1].append(port)
        else:
            groups.append((ou, [port]))
    signals = ",".join(sorted(head["signals"], key=int))
    ous = " | ".join(f"OU: {ou} Ports: {','.join(p)}" for ou, p in groups)
    return f"Node: {head['node']} Signal: {signals} | {ous}"


def planned_masts(heads: dict[str, dict]) -> dict[str, list[str]]:
    masts: dict[str, list[tuple[int, str]]] = {}
    for name, h in heads.items():
        masts.setdefault(h["mast"], []).append((ROLE_ORDER[h["role"]], name))
    return {m: [n for _o, n in sorted(v)] for m, v in masts.items()}


# every level's internal heads (ADR-024; hartlib.level_masts.HEAD_PREFIXES): not wired, so not in the wiring plan
INTERNAL_HEADS = tuple(sorted(set(level_masts.HEAD_PREFIXES.values())))
MASTS = level_masts.PATH


def is_internal_head(system_name: str) -> bool:
    return system_name.startswith(INTERNAL_HEADS)


def is_internal_mast(system_name: str) -> bool:
    heads = level_masts.mast_heads(system_name)
    return bool(heads) and all(is_internal_head(h) for h in heads)


def internal_heads(path: Path = MASTS) -> dict[str, list[str]]:
    """{mast: [head system names]} of masts.csv's rows on internal heads, every level (hartlib.level_masts.read)."""
    return {r["mast"]: [h for h, _u in r["heads"]] for r in level_masts.read(path)
            if is_internal_mast(r["system_name"])}


def read_tables(
    root: ET.Element,
) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """(head system name -> comment, head mast userName -> head names, problems)."""
    head_comments: dict[str, str] = {}
    for el in tables.signal_heads(root):
        sn = tables.text(el, "systemName")
        if sn:
            head_comments[sn] = tables.text(el, "comment")
    masts: dict[str, list[str]] = {}
    bad: list[str] = []
    for el in tables.masts(root, tags=("signalmast",)):
        sn = tables.text(el, "systemName")
        if not sn.startswith("IF$shsm:"):
            continue
        user = tables.user_name(el) or sn
        m = SHSM_RE.match(sn)
        if not m and not is_internal_mast(sn):
            bad.append(f"{user}: head mast {sn} does not name its heads by IH number")
            continue
        if user in masts:
            bad.append(f"{user}: two head masts share this userName")
            continue
        masts[user] = re.findall(r"IH\d+", m.group(1)) if m and "IH:" not in sn else level_masts.mast_heads(sn)
    return head_comments, masts, bad


DIRECTIONS = ("East", "West")       # the word a mast's comment carries after its place (tables_build.with_direction)


def mast_places(root: ET.Element) -> dict[str, str]:
    """{head system name: its head mast's place}, the mast's comment without its direction, as a wired head's
    comment starts (tables_build.bean_comment)."""
    out: dict[str, str] = {}
    for el in tables.masts(root, tags=("signalmast",)):
        place = " | ".join(x for x in tables.text(el, "comment").split(" | ") if x and x not in DIRECTIONS)
        for h in re.findall(r"\(([^()]+)\)", tables.text(el, "systemName")):
            if place:
                out.setdefault(h, place)
    return out


def problems(wiring_rows: list[dict[str, str]], tables_root: ET.Element) -> list[str]:
    heads = load_wiring(wiring_rows)
    plan = planned_masts(heads)
    head_comments, masts, out = read_tables(tables_root)
    places = mast_places(tables_root)

    for mast, want in sorted(plan.items()):
        have = masts.get(mast)
        if have is None:
            out.append(f"{mast}: wired mast missing from tables.xml")
            continue
        if have != want:
            out.append(f"{mast}: heads {' '.join(have)}, wiring plan {' '.join(want)}")

    internal = internal_heads()
    for mast in sorted(set(masts) - set(plan)):
        have = masts[mast]
        if have and all(is_internal_head(h) for h in have):
            if internal.get(mast) != have:      # internal until wired, every level: as masts.csv gives them
                out.append(f"{mast}: internal heads {' '.join(have)}, {MASTS.name} "
                           f"{' '.join(internal.get(mast) or ['none'])}")
            continue
        out.append(f"{mast}: head mast {' '.join(have)} has no head in wiring.csv")

    on_mast = {h for hs in masts.values() for h in hs}
    for name, h in sorted(heads.items()):
        if name not in head_comments:
            out.append(f"{name} ({h['mast']} {h['role']}): wired head not defined in tables.xml")
            continue
        if name not in on_mast:
            out.append(f"{name} ({h['mast']} {h['role']}): wired head is on no mast")
        comment = expected_comment(h)
        place = places.get(name)        # a wired head reads its mast's place first: "Plane | Switch 5 | Node: 4 ..."
        if place:
            comment = f"{place} | {comment}"
        got = head_comments[name]
        if got != comment:
            out.append(f"{name}: comment {head_comments[name]!r}, wiring {comment!r}")
    return out


def main() -> int:
    tables_xml = paths.TABLES_XML
    for p in (paths.WIRING, tables_xml):
        if not p.is_file():
            print(f"MISSING: {p}", file=sys.stderr)
            return 2
    try:
        rows = wiring.digicon_rows()
        found = problems(rows, tables.read(tables_xml))
    except (WiringError, FactsError) as e:
        print(f"FAIL: wiring.csv: {e}")
        return 1
    n_heads = len(load_wiring(rows))
    if found:
        print(f"FAIL: {len(found)} signal head(s) disagree with wiring.csv")
        for line in found:
            print(f"  - {line}")
        return 1
    print(f"OK: {n_heads} wired heads match tables.xml (IH number, mast, comment)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
