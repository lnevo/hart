"""Build freight-car card descriptions (hopper coverage, length, etc.)."""

from __future__ import annotations


def normalize_car_type(car_type: str) -> str:
    t = car_type.strip()
    if t == "Coal":
        return "Hopper"
    return t


def hopper_is_covered(row: dict) -> bool:
    car_class = (row.get("car_class") or "").strip().upper()
    notes = (row.get("notes") or "").lower()
    car_type = normalize_car_type(row.get("car_type") or "")

    if car_type != "Hopper":
        return False

    if car_class == "LO":
        return True
    if car_class == "HT":
        return False
    if "covered" in notes or "cement" in notes or "kosmos" in notes:
        return True
    if any(k in notes for k in ("coke", "coal", "gla", "open-top", "open top")):
        return False
    return False


def hopper_type_label(row: dict) -> str:
    if hopper_is_covered(row):
        return "Cov Hopper"
    return "Hopper"


def is_hopper_row(row: dict) -> bool:
    return normalize_car_type(row.get("car_type") or "") == "Hopper"


def format_type_label(car_type: str) -> str:
    t = normalize_car_type(car_type)
    if not t:
        return ""
    if t == "Tank":
        return "Tank Car"
    if t == "Coil":
        return "Coil Car"
    low = t.lower()
    if low.endswith("car") and " " not in t:
        return f"{t[:-3]} Car"
    return t


def _length_ft(row: dict, car: dict | None) -> str:
    if car and car.get("roster_length_ft"):
        return car["roster_length_ft"]
    if car and car.get("length_ft"):
        return car["length_ft"]
    return (row.get("roster_length_ft") or "").strip()


def build_freight_description(row: dict, car: dict | None = None) -> str:
    """Standard card description for freight cars (not locomotives)."""
    override = row.get("full_name", "").strip()
    if override:
        return override

    color = row.get("color", "").strip()
    length = _length_ft(row, car)

    if is_hopper_row(row):
        parts: list[str] = []
        if color:
            parts.append(color)
        parts.append(hopper_type_label(row))
        if length:
            parts.append(f"{length}'")
        return " · ".join(parts) if parts else "—"

    ctype = normalize_car_type(
        (car or {}).get("car_type") or row.get("car_type", "")
    )
    parts = []
    if color:
        parts.append(color)
    if ctype:
        parts.append(format_type_label(ctype))
    if length:
        parts.append(f"{length}'")
    return " · ".join(parts) if parts else "—"
