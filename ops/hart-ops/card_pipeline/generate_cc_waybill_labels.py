#!/usr/bin/env python3
"""Print STS CC/WB shipment waybills as slim poker-sticker labels.

Source: same data as Reports → CC/WB Waybills based on Shipments
(``printable_ccwaybill.php``), which pairs an empty-car bill with a freight
bill. Here each half is one car-card-sized label on the Apostrophe sticker
sheet (same template as equipment cards).

Data: ``archive/docs/cc_shipments.json`` (refresh from live STS with
``--refresh`` when Docker is up).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table

import generate_card_template as g

BASE = Path(__file__).resolve().parent.parent
SHIPMENTS_JSON = BASE / "archive" / "docs" / "cc_shipments.json"
OUTPUT = BASE / "archive" / "docs" / "HART_CC_Waybill_Labels.docx"
LOGO_MAP = BASE / "operator_logos" / "party_logo_map.json"
HART_LOGO = BASE / "operator_logos" / "hart.png"
CARDS_PER_PAGE = 9

_PARTY_LOGOS: dict[str, str] | None = None


def _load_party_logos() -> dict[str, str]:
    global _PARTY_LOGOS
    if _PARTY_LOGOS is not None:
        return _PARTY_LOGOS
    if LOGO_MAP.exists():
        data = json.loads(LOGO_MAP.read_text(encoding="utf-8"))
        _PARTY_LOGOS = dict(data.get("by_party") or {})
    else:
        _PARTY_LOGOS = {}
    return _PARTY_LOGOS


def _logo_for_party(party: str) -> str:
    """Return absolute path to a party logo, falling back to HART."""
    party = (party or "").strip()
    logos = _load_party_logos()
    rel = logos.get(party, "")
    if rel:
        path = BASE / rel
        if path.exists():
            return str(path)
    if HART_LOGO.exists():
        return str(HART_LOGO)
    if g.LOGO.exists():
        return str(g.LOGO)
    return ""


def _normalize_staging(track: str, spot: str, *, bill_kind: str) -> tuple[str, str, str]:
    """Keep STS staging IN/OUT aligned with empty vs freight flow.

    Empty bill → car goes to the *loading* spot (STAGING IN offline).
    Freight bill → car goes to the *unloading* spot (STAGING OUT offline).
    Non-staging tracks (INBOUND/OUTBOUND/island) are left unchanged.
    """
    track = (track or "").strip()
    spot = (spot or "").strip()
    flow = ""
    if track.lower() == "staging":
        track = "STAGING"
        if bill_kind == "empty":
            spot = "IN"
            flow = "IN"
        elif bill_kind == "freight":
            spot = "OUT"
            flow = "OUT"
        else:
            flow = spot.upper() if spot.upper() in {"IN", "OUT"} else ""
    elif spot.upper() in {"IN", "OUT"}:
        flow = spot.upper()
    return track, spot, flow


def refresh_shipments_from_sts(dest: Path = SHIPMENTS_JSON) -> int:
    """Pull current shipments from the STS web container into JSON."""
    php = r"""
require "/var/www/html/sts/open_db.php";
$dbc = open_db();
$sql = "SELECT s.id, s.code,
  COALESCE(c.description,\"\") AS consignment,
  COALESCE(cc.code,\"\") AS car_code,
  COALESCE(loc_u.code,\"\") AS unload_loc,
  COALESCE(rout_u.station,\"\") AS unload_sta,
  COALESCE(loc_u.track,\"\") AS unload_trk,
  COALESCE(loc_u.spot,\"\") AS unload_spot,
  COALESCE(NULLIF(loc_u.rpt_station,\"\"), rout_u.station, \"\") AS unload_rpt,
  COALESCE(loc_l.code,\"\") AS load_loc,
  COALESCE(rout_l.station,\"\") AS load_sta,
  COALESCE(loc_l.track,\"\") AS load_trk,
  COALESCE(loc_l.spot,\"\") AS load_spot,
  COALESCE(NULLIF(loc_l.rpt_station,\"\"), rout_l.station, \"\") AS load_rpt,
  COALESCE(s.special_instructions,\"\") AS special,
  COALESCE(loc_u.color,\"\") AS unload_color,
  COALESCE(loc_l.color,\"\") AS load_color,
  COALESCE(s.description,\"\") AS description,
  COALESCE(s.remarks,\"\") AS remarks
FROM shipments s
LEFT JOIN commodities c ON c.id = s.consignment
LEFT JOIN car_codes cc ON cc.id = s.car_code
LEFT JOIN locations loc_u ON loc_u.id = s.unloading_location
LEFT JOIN routing rout_u ON rout_u.id = loc_u.station
LEFT JOIN locations loc_l ON loc_l.id = s.loading_location
LEFT JOIN routing rout_l ON rout_l.id = loc_l.station
ORDER BY s.code";
$rs = mysqli_query($dbc, $sql);
$out = [];
while ($row = mysqli_fetch_assoc($rs)) { $out[] = $row; }
file_put_contents("/tmp/cc_shipments.json", json_encode($out, JSON_UNESCAPED_UNICODE));
echo count($out);
"""
    count = subprocess.check_output(
        ["docker", "exec", "sts-docker-web-1", "php", "-r", php],
        text=True,
    ).strip()
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["docker", "cp", "sts-docker-web-1:/tmp/cc_shipments.json", str(dest)]
    )
    return int(count)


def _station(rpt: str, station: str) -> str:
    rpt = (rpt or "").strip()
    return rpt if rpt else (station or "").strip()


def labels_from_shipments(shipments: list[dict]) -> list[dict]:
    """Two labels per shipment: empty (mtybill) then freight (waybill).

    STS is the source of truth for locations/commodities/car codes. Staging
    spots are normalized so empty bills are Staging IN and freight bills are
    Staging OUT (matching CC/WB flow).
    """
    labels: list[dict] = []
    for s in shipments:
        code = (s.get("code") or "").strip()
        consignment = (s.get("consignment") or "").strip()
        car_code = (s.get("car_code") or "").strip()

        load_party = _station(s.get("load_rpt", ""), s.get("load_sta", ""))
        unload_party = _station(s.get("unload_rpt", ""), s.get("unload_sta", ""))

        # Empty bill → empty car goes TO the loading location (STS mtybill).
        e_track, e_spot, e_flow = _normalize_staging(
            s.get("load_trk", ""), s.get("load_spot", ""), bill_kind="empty"
        )
        labels.append(
            {
                "BillKind": "empty",
                "ShipmentCode": code,
                "ToLocation": (s.get("load_loc") or "").strip(),
                "Station": load_party,
                "Track": e_track,
                "Spot": e_spot,
                "Flow": e_flow,
                "CarCode": car_code,
                "Consignment": consignment,
                "Color": (s.get("load_color") or "").strip(),
                "Description": (s.get("description") or "").strip(),
                "LogoParty": load_party,
                "LogoPath": _logo_for_party(load_party),
            }
        )

        # Freight bill → load goes TO the unloading location (STS waybill).
        f_track, f_spot, f_flow = _normalize_staging(
            s.get("unload_trk", ""), s.get("unload_spot", ""), bill_kind="freight"
        )
        labels.append(
            {
                "BillKind": "freight",
                "ShipmentCode": code,
                "ToLocation": (s.get("unload_loc") or "").strip(),
                "Station": unload_party,
                "Track": f_track,
                "Spot": f_spot,
                "Flow": f_flow,
                "CarCode": car_code,
                "Consignment": consignment,
                "FromLocation": (s.get("load_loc") or "").strip(),
                "FromStation": load_party,
                "Color": (s.get("unload_color") or "").strip(),
                "Description": (s.get("description") or "").strip(),
                "Special": (s.get("special") or "").strip(),
                "LogoParty": unload_party,
                "LogoPath": _logo_for_party(unload_party),
            }
        )
    return labels


def _pad_to_page(deck: list[dict]) -> list[dict]:
    need = (CARDS_PER_PAGE - len(deck) % CARDS_PER_PAGE) % CARDS_PER_PAGE
    if not need:
        return deck
    out = deck[:]
    for _ in range(need):
        out.append(
            {
                "BillKind": "freight",
                "ShipmentCode": "",
                "ToLocation": "",
                "Station": "",
                "Track": "",
                "Spot": "",
                "CarCode": "",
                "Consignment": "",
                "FromLocation": "",
                "FromStation": "",
                "Color": "lightgrey",
            }
        )
    return out


def _set_page_break_before_table(tbl) -> None:
    first_row = tbl.findall(qn("w:tr"))[0]
    first_cell = first_row.findall(qn("w:tc"))[0]
    p = first_cell.find(qn("w:p"))
    if p is None:
        p = OxmlElement("w:p")
        first_cell.insert(0, p)
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p.insert(0, pPr)
    if pPr.find(qn("w:pageBreakBefore")) is None:
        pPr.insert(0, OxmlElement("w:pageBreakBefore"))


def _append_grid(doc: Document, grid_xml) -> Table:
    body = doc.element.body
    tbl = deepcopy(grid_xml)
    _set_page_break_before_table(tbl)
    g._insert_before_sect(body, tbl)
    g._ensure_sect_pr_last(body)
    table = Table(body.findall(qn("w:tbl"))[-1], doc)
    g.strip_grid_guides(table)
    return table


def _blank_sticker_grid():
    scratch_path = BASE / ".scratch_cc_waybill.docx"
    shutil.copy2(g.STICKER_SHEET, scratch_path)
    scratch = Document(scratch_path)
    g.keep_sticker_grid(scratch)
    grid = deepcopy(scratch.tables[0]._tbl)
    scratch_path.unlink(missing_ok=True)
    return grid


def _fill_page(sheet: Table, batch: list[dict], page_idx: int) -> None:
    for i, record in enumerate(batch):
        r, c = g.CARD_SLOTS[i]
        g.build_cc_waybill_label(
            sheet.rows[r].cells[c],
            idx=page_idx * CARDS_PER_PAGE + i,
            record=record,
        )


def generate(labels: list[dict], output: Path = OUTPUT) -> None:
    g.require_sticker_sheet()

    deck = _pad_to_page(labels)
    blank_grid = _blank_sticker_grid()
    temp_path = output.with_suffix(".tmp.docx")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(g.STICKER_SHEET, temp_path)
    doc = Document(temp_path)
    g.keep_sticker_grid(doc)

    pages = [deck[i : i + CARDS_PER_PAGE] for i in range(0, len(deck), CARDS_PER_PAGE)]
    sheet = doc.tables[0]
    _fill_page(sheet, pages[0], 0)
    for page_idx, batch in enumerate(pages[1:], start=1):
        sheet = _append_grid(doc, blank_grid)
        _fill_page(sheet, batch, page_idx)

    g._add_document_tail(doc.element.body)
    doc.save(temp_path)
    os.replace(temp_path, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-export shipments from the live STS Docker DB before printing",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=SHIPMENTS_JSON,
        help=f"Shipments JSON (default: {SHIPMENTS_JSON})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help=f"Output docx (default: {OUTPUT})",
    )
    args = parser.parse_args()

    if args.refresh or not args.json.exists():
        n = refresh_shipments_from_sts(args.json)
        print(f"Refreshed {n} shipments → {args.json}")

    shipments = json.loads(args.json.read_text(encoding="utf-8"))
    labels = labels_from_shipments(shipments)
    generate(labels, args.output)

    empties = sum(1 for L in labels if L["BillKind"] == "empty")
    freights = sum(1 for L in labels if L["BillKind"] == "freight")
    pages = (len(_pad_to_page(labels)) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    print(f"Wrote {args.output}")
    print(
        f"  {len(shipments)} shipments → {empties} empty + {freights} freight "
        f"labels · {pages} sticker pages (9/page)"
    )


if __name__ == "__main__":
    main()
