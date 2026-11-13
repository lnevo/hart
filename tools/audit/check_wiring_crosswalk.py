#!/usr/bin/env python3
"""Signal heads in tables.xml must follow the wiring plan.

The IH number of a head is its MQTT topic (track/signalhead/<packed>), and the
wiring rule is packed = cabinet radio address x 100 + slot
(docs/wiring/README.md). docs/wiring/signals/signal_wiring.csv holds that
number for every head as system_name. This check fails when:

- a physical mast (a SignalHeadSignalMast named in signal_wiring.csv) carries
  a head other than its planned head, in planned order (top, bottom);
- a SignalHeadSignalMast in tables.xml is not in the wiring plan;
- a wired mast is missing from tables.xml;
- a wired head is not defined, or is on no mast;
- a wired head's comment disagrees with its node, signal and port list;
- a wiring row's system_name, packed (node x 100 + uid) and topic disagree.

Hidden virtual masts (IF$vsm) carry no wiring and are not checked.
Mast 6LB is an interim one-low dwarf on its top head (IH432) until the bottom
head is wired; its bottom head IH433 stays defined and on no mast.
"""
from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_HARTLIB = next(p / "tools/hartlib/src" for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir())
sys.path.insert(0, str(_HARTLIB))

from hartlib import paths, tables  # noqa: E402

# Masts that may show only their first planned heads for now.
INTERIM_PREFIX_MASTS = {"Mast 6LB"}

ROLE_ORDER = {"T": 0, "S": 0, "B": 1}
SHSM_RE = re.compile(r"^IF\$shsm:[^:]+:[^(]+((?:\(IH\d+\))+)$")


class WiringError(ValueError):
    """signal_wiring.csv contradicts itself."""


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
        if not m:
            bad.append(f"{user}: head mast {sn} does not name its heads by IH number")
            continue
        if user in masts:
            bad.append(f"{user}: two head masts share this userName")
            continue
        masts[user] = re.findall(r"IH\d+", m.group(1))
    return head_comments, masts, bad


def problems(wiring_rows: list[dict[str, str]], tables_root: ET.Element) -> list[str]:
    heads = load_wiring(wiring_rows)
    plan = planned_masts(heads)
    head_comments, masts, out = read_tables(tables_root)

    for mast, want in sorted(plan.items()):
        have = masts.get(mast)
        if have is None:
            out.append(f"{mast}: wired mast missing from tables.xml")
            continue
        ok = have == want or (
            mast in INTERIM_PREFIX_MASTS and have and have == want[: len(have)]
        )
        if not ok:
            out.append(f"{mast}: heads {' '.join(have)}, wiring plan {' '.join(want)}")

    for mast in sorted(set(masts) - set(plan)):
        out.append(f"{mast}: head mast {' '.join(masts[mast])} is not in signal_wiring.csv")

    on_mast = {h for hs in masts.values() for h in hs}
    for name, h in sorted(heads.items()):
        if name not in head_comments:
            out.append(f"{name} ({h['mast']} {h['role']}): wired head not defined in tables.xml")
            continue
        interim_off = h["mast"] in INTERIM_PREFIX_MASTS and h["role"] == "B"
        if name not in on_mast and not interim_off:
            out.append(f"{name} ({h['mast']} {h['role']}): wired head is on no mast")
        want = expected_comment(h)
        if head_comments[name] != want:
            out.append(f"{name}: comment {head_comments[name]!r}, wiring {want!r}")
    return out


def main() -> int:
    wiring = paths.SIGNAL_WIRING
    tables_xml = paths.TABLES_XML
    for p in (wiring, tables_xml):
        if not p.is_file():
            print(f"MISSING: {p}", file=sys.stderr)
            return 2
    with wiring.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    try:
        found = problems(rows, tables.read(tables_xml))
    except WiringError as e:
        print(f"FAIL: signal_wiring.csv: {e}")
        return 1
    n_heads = len(load_wiring(rows))
    if found:
        print(f"FAIL: {len(found)} signal head(s) disagree with signal_wiring.csv")
        for line in found:
            print(f"  - {line}")
        return 1
    print(f"OK: {n_heads} wired heads match tables.xml (IH number, mast, comment)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
