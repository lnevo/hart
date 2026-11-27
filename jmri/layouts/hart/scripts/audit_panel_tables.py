"""audit_panel_contracts checks of the tables' own settings: MQTT sensor names, turnout feedback and lookups, the LCC
turnout aliases, the CATS occupancy bindings, continuing legs and routing, and the panel's labels.

audit_panel_contracts.py imports this from its own folder (paths.LAYOUT_SCRIPTS) and runs each check from
audit_source.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from audit_panel_base import Audit, first_items, text
from hartlib import devices, levels, occupancy_bindings, railroad_facts, tables
from lcc_turnout_contract import contract_violations

# Packed MQTT 467–469 are not JMRI beans. Do not create them in tables.xml.
FORBIDDEN_MQTT_SENSORS = ("M2S467", "M2S468", "M2S469")
MQTT_SENSOR_SYSNAME = re.compile(r"^M2S\d+$")


def occupancy_binding_map() -> dict[str, str]:
    """{block name: occupancy sensor} of the blocks the CATS desks bind (hartlib.occupancy_bindings: the block rows of
    the device master with a cats_discipline)."""
    return {r["block_user_name"]: r["occupancy_sensor_user_name"] for r in occupancy_bindings.rows()}


def audit_forbidden_mqtt_sensors(root: ET.Element, audit: Audit) -> None:
    found: list[str] = []
    garbage: list[str] = []
    for sensors in root.findall("sensors"):
        cls = sensors.get("class") or ""
        if "MqttSensor" not in cls:
            continue
        for sensor in sensors.findall("sensor"):
            sysn = text(sensor, "systemName") or (sensor.get("systemName") or "").strip()
            if not sysn:
                continue
            if sysn in FORBIDDEN_MQTT_SENSORS:
                found.append(sysn)
            elif not MQTT_SENSOR_SYSNAME.fullmatch(sysn):
                garbage.append(sysn)
    if found:
        audit.error(
            "do not add MQTT sensors "
            + ", ".join(FORBIDDEN_MQTT_SENSORS)
            + f"; found {sorted(set(found))}"
        )
    if garbage:
        audit.error(
            "MQTT sensor systemNames must be M2S plus digits "
            "(not M2SBlock 1-1); "
            f"found {sorted(set(garbage))}"
        )


# Layout Editor stores continuingSense as the JMRI constant (CLOSED=2, THROWN=4, UNKNOWN=1); "1" draws both legs and
# ignores the table's Closed/Thrown. CLOSED is the continuing (through) leg of the Princess turnouts (Switch 37 and
# 39, DCC 114 and 115) and of the crossovers of Switch 7, 23 and 35 (MQTT CLOSED = through mains). The staging
# switch numbers; their Layout Editor idents are switches.csv's le_ident (continuing_closed_idents).
CONTINUING_CLOSED_SWITCHES = (39, 37, 23, 35, 7)
AAR_2_HEAD = "IF$shsm:AAR-1946:SL-2-high-abs"
AAR_2_HEAD_DISABLED = ("Clear Alt", "Advance Approach Medium", "Approach Medium", "Advance Approach", "Medium Clear",
                       "Medium Approach", "Restricting")


def continuing_closed_idents(path: Path | None = None) -> tuple[str, ...]:
    """The Layout Editor idents of CONTINUING_CLOSED_SWITCHES: their staging rows' le_ident in switches.csv (`path`,
    default this checkout's). FactsError when one of them has no staging row with an le_ident."""
    rows = railroad_facts.read_switch_rows(railroad_facts.Sources.under().switches if path is None else path)
    ident = {r.switch: r.le_ident for r in rows
             if r.level == levels.STAGING and r.switch in CONTINUING_CLOSED_SWITCHES and r.le_ident}
    missing = [n for n in CONTINUING_CLOSED_SWITCHES if n not in ident]
    if missing:
        raise railroad_facts.FactsError(f"switches.csv gives no staging le_ident for Switch "
                                        f"{', '.join(map(str, missing))}")
    return tuple(ident[n] for n in CONTINUING_CLOSED_SWITCHES)


def audit_generated_settings(root: ET.Element, audit: Audit, switches: Path | None = None) -> None:
    """The settings nothing else guards: continuing="2" on the Princess turnouts and the crossovers
    (continuing_closed_idents, from switches.csv `switches`), Layout Block advanced routing on (SML Discover needs
    it), and the disabled aspects of AAR 2-head masts."""
    try:
        closed = continuing_closed_idents(switches)
    except (railroad_facts.FactsError, OSError) as exc:
        audit.error(f"continuing turnouts: {exc}")
        closed = ()
    for turnout in root.iter("layoutturnout"):
        if turnout.get("ident") in closed and turnout.get("continuing") != "2":
            audit.error(f"layoutturnout {turnout.get('ident')} has continuing={turnout.get('continuing')!r}, not "
                        "'2' (CLOSED = through; '1' is UNKNOWN and draws both legs)")
    blocks = next(root.iter("layoutblocks"), None)
    if blocks is None:
        audit.error("no layoutblocks element (SML Discover needs advanced routing on)")
    elif blocks.get("blockrouting") != "yes":
        audit.error(f'layoutblocks blockrouting is {blocks.get("blockrouting")!r}, not "yes" (SML Discover needs '
                    "advanced routing)")
    for mast in root.iter("signalmast"):
        name = text(mast, "systemName")
        if name.startswith(AAR_2_HEAD):
            off = {a.text for a in mast.iter("disabledAspect")}
            if missing := [a for a in AAR_2_HEAD_DISABLED if a not in off]:
                audit.error(f"AAR 2-head mast {name} does not disable aspects {missing}")


def audit_occupancy_bindings(root: ET.Element, audit: Audit, *, required: bool) -> None:
    """The occupancy sensor hartlib.occupancy_bindings gives each block the CATS desks bind must be its JMRI block's
    occupancysensor."""
    problem = audit.reporter(required)
    expected = occupancy_binding_map()
    found: dict[str, set[str]] = {}
    for block in root.findall("./blocks/block"):
        name = text(block, "userName")
        occ = text(block, "occupancysensor")
        if name and occ:
            found.setdefault(name, set()).add(occ)
    mismatches: list[str] = []
    for name, sensor in sorted(expected.items()):
        actual = found.get(name, set())
        if not actual:
            continue
        if actual != {sensor}:
            mismatches.append(f"{name}: master {sensor!r}, xml {sorted(actual)}")
    if mismatches:
        problem("the device master's CATS bindings disagree with block occupancysensor: " + first_items(mismatches))
    audit.facts["occupancy_bindings"] = tuple(sorted(expected.items()))


def audit_turnout_feedback_sensors(root: ET.Element, audit: Audit, *, required: bool) -> None:
    """TWOSENSOR sensor1/sensor2 must resolve to existing sensor userNames.

    Stale names make OpenLCB invent systemNames like MSSwitch 4-1 FB R.
    """
    problem = audit.reporter(required)
    sensor_names = {
        text(sensor, "userName")
        for sensor in root.iter("sensor")
        if text(sensor, "userName")
    }
    missing: list[str] = []
    stale_old: list[str] = []
    for turnout in root.iter("turnout"):
        ident = text(turnout, "userName") or text(turnout, "systemName") or "?"
        for attr in ("sensor1", "sensor2"):
            name = (turnout.get(attr) or "").strip()
            if not name:
                continue
            if re.fullmatch(r"Switch \d+-\d+ FB [NR]", name):
                stale_old.append(f"{ident} {attr}={name}")
            if name not in sensor_names:
                missing.append(f"{ident} {attr}={name}")
    if stale_old:
        problem("turnout feedback still uses pre-convert FB userNames: " + first_items(stale_old))
    elif missing:
        problem("turnout feedback sensors are not sensor userNames: " + first_items(missing))
    audit.facts["turnout_feedback"] = tuple(sorted(missing or stale_old))


def audit_turnout_systemname_lookups(root: ET.Element, audit: Audit, *, required: bool) -> None:
    """Block-path and route turnout lookups must resolve to a live turnout.

    JMRI may store M2T* or the public userName (Switch 13). Old convert names
    (Switch 116) do not resolve and make OpenLCB invent MTSwitch 116.
    """
    problem = audit.reporter(required)
    real_sys: set[str] = set()
    real_user: set[str] = set()
    for manager in root.findall("turnouts"):
        for turnout in manager.findall("turnout"):
            sn = text(turnout, "systemName") or (turnout.get("systemName") or "").strip()
            un = text(turnout, "userName")
            if sn:
                real_sys.add(sn)
            if un:
                real_user.add(un)
    missing: list[str] = []
    for setting in root.iter("beansetting"):
        path_turnout = setting.find("turnout")
        if path_turnout is None:
            continue
        sn = (path_turnout.get("systemName") or text(path_turnout, "systemName")).strip()
        if sn and sn not in real_sys and sn not in real_user:
            missing.append(f"path {sn}")
    for route_to in root.iter("routeOutputTurnout"):
        sn = (route_to.get("systemName") or "").strip()
        if sn and sn not in real_sys and sn not in real_user:
            missing.append(f"route {sn}")
    if missing:
        problem("turnout lookups do not resolve to a turnout systemName or userName: " + first_items(missing))
    audit.facts["turnout_lookups"] = tuple(sorted(missing))


def audit_lcc_mqtt_turnout_aliases(root: ET.Element, audit: Audit, *, required: bool) -> None:
    """Every MQTT DCC turnout has MTT{dcc} named and wired from the device map."""
    problem = audit.reporter(required)
    csv_path = devices.MASTER
    issues = contract_violations(root, csv_path)
    if issues:
        problem("LCC turnout aliases do not match MQTT plants / device map: " + first_items(issues))
    audit.facts["lcc_turnout_aliases"] = tuple(issues)


def audit_block_contents_visible(panel: ET.Element | None, audit: Audit) -> None:
    """Tracks paint at level 3; labels at 0 sit behind the panel background. Black text, in the plugin's Dialog font
    or JMRI's default."""
    if panel is None:
        return
    _, errors = tables.ensure_block_contents_visible(panel, check=True)
    for message in errors:
        audit.error(message)


def audit_placeholders(panel: ET.Element | None, audit: Audit) -> None:
    placeholders: list[str] = []
    redundant_occupancy_icons: list[str] = []
    # Intentional status-lamp captions (not temporary SIG… placeholders).
    _status_lamp_labels = {"LCOS", "Turnouts", "Signals", "Track Power"}
    if panel is not None:
        for label in panel.iter("positionablelabel"):
            value = (label.get("text") or text(label, "text")).strip()
            if value in _status_lamp_labels:
                continue
            if value.upper().startswith("SIG"):
                placeholders.append(value)
        for icon in panel.iter("sensoricon"):
            name = (icon.get("sensor") or "").strip()
            if re.fullmatch(r"Block \d+-\d+", name):
                redundant_occupancy_icons.append(name)
    if placeholders:
        audit.warn(f"stale SIG placeholder labels remain: {sorted(placeholders)}")
    if redundant_occupancy_icons:
        audit.error(
            "sensoricon still bound to retired Block n-n userNames "
            "(JMRI MQTT auto-creates M2SBlock n-n); "
            f"{sorted(redundant_occupancy_icons)}"
        )
    audit.facts["sig_placeholders"] = tuple(sorted(placeholders))
    audit.facts["occupancy_sensor_icons"] = tuple(
        sorted(redundant_occupancy_icons)
    )
