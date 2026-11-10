"""JMRI car roster id helpers (road code + id = roadName + roadNumber)."""

from __future__ import annotations

from process_car_images import ROAD_ALIASES, _norm


def road_code(row: dict) -> str:
    roster_road = (row.get("roster_road") or "").strip()
    if roster_road:
        return roster_road
    marks = (row.get("reporting_marks") or row.get("road_name") or "").strip()
    if not marks:
        return ""
    return ROAD_ALIASES.get(marks) or ROAD_ALIASES.get(_norm(marks), _norm(marks))


def manifest_car_id(row: dict) -> str:
    rid = (row.get("roster_id") or "").strip()
    if rid:
        return rid
    rc = road_code(row)
    num = (row.get("road_number") or "").strip()
    if rc and num:
        return f"{rc}{num}"
    return ""


def assign_freight_roster_id(row: dict) -> None:
    """Set roster_id and roster_road on a manifest row when road/number are known."""
    rid = manifest_car_id(row)
    if not rid:
        return
    row["roster_id"] = rid
    rc = road_code(row)
    if rc:
        row["roster_road"] = rc
