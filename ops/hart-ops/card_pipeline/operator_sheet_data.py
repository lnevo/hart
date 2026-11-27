"""The text tables of the operator sheet (generate_operator_sheet.py): industry logos, page order, summaries,
the Shenango track rows and the yard and desk pages."""

from __future__ import annotations

from typing import NotRequired, TypedDict

import hartlib_path  # noqa: E402

hartlib_path.ensure_on_path()
from hartlib import operations  # noqa: E402


class TrackRow(TypedDict):
    """One row of a track table (an industry with no numbered spots)."""

    track: str
    cars: str
    inbound: str
    outbound: str


class TrainJob(TypedDict):
    """A train on a yard page: its name and the bullet lines under it."""

    name: str
    lines: list[str]


class YardPage(TypedDict):
    """A yard or desk reference page. Colours are RRGGBB; logo is a file in operator_logos/."""

    title: str
    subtitle: str
    accent: str
    text: str
    logo: str | None
    logo_width: float
    role: list[str]
    sections: NotRequired[list[tuple[str, list[str]]]]
    trains: NotRequired[list[TrainJob]]
    blocking: NotRequired[list[str]]
    jobs: NotRequired[list[str]]


# The island industries of the sheet, in their order, with their logos and history notes: ops/hart-ops/data/
# industry_sheet.csv and industry_notes.csv (hartlib.operations), keyed here by the sheet's name for each.
_SHEET = operations.read_industry_sheet()
_NOTES = operations.read_industry_notes()
INDUSTRY_LOGOS: dict[str, tuple[str, float]] = {r.sheet_name: (r.logo, r.logo_width) for r in _SHEET}
SHEET_INDUSTRY_ORDER: dict[str, int] = {r.sheet_name: r.sheet_order for r in _SHEET}
INDUSTRY_SUMMARIES: dict[str, list[str]] = {r.sheet_name: _NOTES.get(r.industry_id, []) for r in _SHEET}

SHENANGO_TRACK_ROWS: list[TrackRow] = [
    {
        "track": "Shipping 1",
        "cars": "HM",
        "inbound": "Empty / reload coke",
        "outbound": "Coke",
    },
    {
        "track": "Shipping 2",
        "cars": "HM",
        "inbound": "Empty / reload coke",
        "outbound": "Coke",
    },
]

# Yard / desk reference pages (after island industries).
# Offline company lists from hart_scully_nville_shipping_map_proposed.csv
# (party tracks at McKees Rocks-PA / Mckeesport-PA — not Neville Island plants).
YARD_PAGES: list[YardPage] = [
    {
        "title": "Scully Yard",
        "subtitle": "POHC interchange · McKees Rocks offline",
        "accent": "FFA500",  # STS orange
        "text": "000000",
        "logo": "pohc.png",
        "logo_width": 1.25,
        "role": [
            "POHC gateway. NVL takes its session-start block here. McKees Rocks-PA "
            "party tracks hold offline suppliers and customers.",
            "Connections beyond the offline tracks are typically POHC and NS.",
        ],
        "sections": [
            (
                "McKees Rocks — inbound (suppliers)",
                [
                    "Allegheny Ludlum (Brackenridge, PA)",
                    "Exxon Chemical (Bayonne, NJ)",
                    "Ferrellgas Co (Taneytown, MD)",
                    "General Chemical (Parsippany, NJ)",
                    "Hillman Coal (Canton Twp, PA)",
                    "Houghton Chemical (Allston, MA)",
                    "Kosmos Cement (Canton, OH)",
                    "Lehigh Cement (Mitchell, IN)",
                    "McConway & Torley (Pittsburgh, PA)",
                    "Michigan Limestone (Rogers City, MI)",
                    "Novacor (Indian Orchard, MA)",
                    "Republic Steel (Cleveland, OH)",
                ],
            ),
            (
                "McKees Rocks — outbound (customers)",
                [
                    "LTV Steel Cleveland Works (Cleveland, OH) — coke",
                    "Owens-Illinois (Toledo, OH)",
                    "Bemis Company (Flemington, NJ)",
                    "Pittsburgh Forge (McKees Rocks, PA)",
                    "Univar (Salem, MA)",
                ],
            ),
        ],
        "jobs": [
            "NVL — assign/pickup session block at Scully, then run to South Yard.",
        ],
    },
    {
        "title": "Demmler Yard",
        "subtitle": "CSX interchange · Mckeesport offline",
        "accent": "0000CD",  # STS mediumblue
        "text": "0000CD",
        "logo": "csx.png",
        "logo_width": 1.55,
        "role": [
            "CSX gateway. D749 lifts its inbound block here at session start. "
            "Mckeesport-PA party tracks hold offline suppliers and customers.",
            "Connections beyond the offline tracks are typically CSX "
            "(URR territory historically adjacent at Mckeesport).",
        ],
        "sections": [
            (
                "Mckeesport — inbound (suppliers)",
                [
                    "BASF (Wyandotte, MI)",
                    "Consol Energy (Pittsburgh, PA)",
                    "Dow Chemical (Midland, MI)",
                    "Ferrellgas pipeline terminal",
                    "Martin Marietta (Clairton, PA)",
                    "Medusa Cement (Charlevoix, MI)",
                    "Metal Service Co. (Apollo, PA)",
                    "R&P Coal (Brady Twp, PA)",
                    "Ryerson Steel Service",
                    "US Aggregates (Indianapolis, IN)",
                    "Washington Steel (Washington, PA)",
                    "Calgon Corp (Columbus, OH)",
                ],
            ),
            (
                "Mckeesport — outbound (customers)",
                [
                    "U.S. Steel Edgar Thomson Works (Braddock, PA) — coke",
                    "Calgon Corp (Columbus, OH)",
                    "Houghton Chemical (Allston, MA)",
                    "Metal Service Co. (Apollo, PA)",
                    "Owens-Illinois (Ottawa, IL)",
                    "Ryerson Steel Service",
                ],
            ),
        ],
        "jobs": [
            "D749 — pickup Demmler block → South Yard setout to open the session; "
            "later return from McKeesport side and terminate West Yard.",
        ],
    },
    {
        "title": "South Yard",
        "subtitle": "Classification hub · session start",
        "accent": "D3D3D3",  # STS lightgrey
        "text": "000000",
        "logo": "hart.png",
        "logo_width": 0.72,
        "role": [
            "Session open / class yard. West Lead = SOUTH-SCALE (CK1 weigh at 4 MPH, "
            "stretch, no brakes). Exchange: Demmler/CSX off; Island/Shenango on.",
        ],
        "trains": [
            {
                "name": "D749 — CSX turn",
                "lines": [
                    "Lift West Yard consist → Demmler pickup → South setout to open ops; "
                    "interchange per YM; west when cleared.",
                    "Return from McKeesport; YM spots West or South; engine to terminal.",
                ],
            },
            {
                "name": "NVL — POHC Island local",
                "lines": [
                    "Scully → South; interchange per YM; work Island industries + "
                    "Shenango setouts.",
                    "Finish Island/Shenango deliveries before return homebound. Final "
                    "South interchange → Scully. Shenango deliver-only on return.",
                ],
            },
            {
                "name": "CK1 — Coke transfer",
                "lines": [
                    "Calibrate scale. Shenango: set out reloads, lift Shipping 1/2 coke → "
                    "weigh West Lead → class. Imbalanced → reload orders.",
                    "Same session: reloads South → Shenango when authorized.",
                ],
            },
        ],
        "blocking": [
            "1. D749 Demmler → South setout opens the session.",
            "2. NVL South exchange before Island work.",
            "3. Island/Shenango setouts before NVL return homebound assigns.",
            "4. CK1 weigh/resort; reloads to Shenango when ready.",
            "5. D749 return → West Yard.",
        ],
    },
    {
        "title": "Dispatcher",
        "subtitle": "HART Railroad · session control",
        "accent": "000000",
        "text": "000000",
        "logo": "hart.png",
        "logo_width": 0.72,
        "role": [
            "Authorize road moves, keep train order, and protect the South Yard block "
            "exchange. Crews work from switch lists; yardmaster owns South class tracks.",
        ],
        "sections": [
            (
                "Territory",
                [
                    "Scully Yard — POHC interchange (NVL start).",
                    "Neville Island / Shenango — NVL local; CK1 coke plant.",
                    "South Yard — class hub, session open, track scale (West Lead).",
                    "Demmler Yard — CSX interchange (D749 start / return).",
                    "West Yard — D749 overnight / terminate.",
                ],
            ),
            (
                "Session sequence",
                [
                    "D749: Demmler pickup → South setout opens ops; then west as cleared.",
                    "NVL: Scully block → South exchange → Island / Shenango work → return "
                    "to Scully (Shenango deliver-only on return).",
                    "CK1: Shenango shipping → South scale → class; reloads back when ready.",
                    "D749 return from McKeesport → West Yard.",
                ],
            ),
        ],
        "blocking": [
            "1. Hold NVL Island work until South has taken the D749 inbound setout "
            "and completed the block exchange.",
            "2. Island / Shenango deliveries before NVL builds the homebound.",
            "3. CK1 scale string clear of West Lead conflicts during weigh (4 MPH).",
            "4. One road move at a time across shared leads when crews meet at South.",
        ],
    },
]
