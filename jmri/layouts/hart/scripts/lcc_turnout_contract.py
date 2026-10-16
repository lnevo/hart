#!/usr/bin/env python3
"""MQTT M2T* plant ↔ OpenLCB MTT{dcc} alias (device map: DCC Switch N).

Every MQTT turnout whose comment has ``DCC: N`` has an LCC twin ``MTT{N}``:
userName ``DCC Switch N``, comment is the MQTT comment without DCC, and the
same feedback sensors as the MQTT bean. Do not delete MTT* as leftovers.
"""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

DCC_RE = re.compile(r"DCC:\s*(\d+)")
DCC_SEG_RE = re.compile(r"\s*\|\s*DCC:\s*\d+\s*")
SWITCH_USER_RE = re.compile(r"^Switch \d+$")


def child_text(element: ET.Element, tag: str) -> str:
    value = element.findtext(tag)
    return value.strip() if value else ""


def lcc_comment_from_mqtt(comment: str) -> str:
    parts = [
        part.strip()
        for part in DCC_SEG_RE.sub("|", comment or "").split("|")
        if part.strip()
    ]
    return " | ".join(parts)


def expected_lcc_user(mqtt_user: str) -> str | None:
    if SWITCH_USER_RE.fullmatch(mqtt_user or ""):
        return f"DCC {mqtt_user}"
    return None


def identity_lcc_rows(csv_path: Path) -> dict[str, tuple[str, str]]:
    """MTT* → (userName, comment) from identity rows (current == proposed)."""
    out: dict[str, tuple[str, str]] = {}
    if not csv_path.is_file():
        return out
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("layer") or "").strip() != "turnout":
                continue
            current = (row.get("current") or "").strip()
            proposed = (row.get("proposed") or "").strip()
            if not current or current != proposed:
                continue
            comment = (row.get("comment") or "").strip()
            for token in (row.get("hardware") or "").split():
                if token.startswith("MTT"):
                    out[token] = (proposed, comment)
    return out


def turnout_index(root: ET.Element) -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for turnout in root.iter("turnout"):
        sn = child_text(turnout, "systemName")
        if sn:
            out[sn] = turnout
    return out


def contract_violations(root: ET.Element, csv_path: Path | None = None) -> list[str]:
    """Return human-readable failures; empty means the contract holds."""
    beans = turnout_index(root)
    mqtt = {sn: el for sn, el in beans.items() if sn.startswith("M2T")}
    lcc = {sn: el for sn, el in beans.items() if sn.startswith("MTT")}
    identity = identity_lcc_rows(csv_path) if csv_path is not None else {}
    problems: list[str] = []
    paired: set[str] = set()

    for sn, el in sorted(mqtt.items()):
        user = child_text(el, "userName")
        comment = child_text(el, "comment")
        match = DCC_RE.search(comment)
        if not match:
            problems.append(f"{sn} ({user or '?'}) comment missing DCC")
            continue
        alias = f"MTT{match.group(1)}"
        paired.add(alias)
        want_user = expected_lcc_user(user)
        want_comment = lcc_comment_from_mqtt(comment)
        if want_user is None:
            problems.append(f"{sn} userName {user!r} is not Switch N")
            continue
        twin = lcc.get(alias)
        if twin is None:
            problems.append(f"{sn} ({user}) has no LCC alias {alias}")
            continue
        got_user = child_text(twin, "userName")
        got_comment = child_text(twin, "comment")
        if got_user != want_user:
            problems.append(f"{alias} userName {got_user!r} expected {want_user!r}")
        if got_comment != want_comment:
            problems.append(
                f"{alias} comment {got_comment!r} expected {want_comment!r}"
            )
        mqtt_fb = el.get("feedback") or ""
        lcc_fb = twin.get("feedback") or ""
        if lcc_fb != mqtt_fb:
            problems.append(f"{alias} feedback {lcc_fb!r} expected {mqtt_fb!r}")
        if mqtt_fb == "TWOSENSOR":
            for attr in ("sensor1", "sensor2"):
                want = el.get(attr) or ""
                got = twin.get(attr) or ""
                if got != want:
                    problems.append(f"{alias} {attr} {got!r} expected {want!r}")
        else:
            for attr in ("sensor1", "sensor2"):
                got = twin.get(attr) or ""
                if got:
                    problems.append(f"{alias} {attr}={got!r} but MQTT is {mqtt_fb}")
        if alias in identity:
            map_user, map_comment = identity[alias]
            if got_user != map_user:
                problems.append(
                    f"{alias} userName {got_user!r} != device map {map_user!r}"
                )
            if got_comment != map_comment:
                problems.append(
                    f"{alias} comment {got_comment!r} != device map {map_comment!r}"
                )
        elif csv_path is not None:
            problems.append(f"{alias} missing identity row in {csv_path.name}")

    extra = sorted(set(lcc) - paired)
    for alias in extra:
        problems.append(f"{alias} has no MQTT plant with matching DCC")
    if csv_path is not None:
        for alias in sorted(set(identity) - paired):
            problems.append(f"{alias} identity row has no MQTT plant with matching DCC")
    return problems
