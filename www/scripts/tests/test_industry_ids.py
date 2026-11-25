"""The copies of ops/hart-ops/data/industries.csv agree with it (ADR-039).

check_data.py checks each industry_id exists. This checks what a single-column ref cannot: that a row's name
matches its id's row (through the alias list while the old spellings last), that a waybill's spots are spots of its industry, and that the site's industries.json
carries each industry once, under its public name, slug and blurb, with the waybill count and commodities the waybill
list gives.
"""
import csv
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "ops" / "hart-ops" / "data"
INTERCHANGE_HEADER = "INTERCHANGE"  # waybill_data.INTERCHANGE_HEADER: the card header of the through cards

# Old spellings the spot and waybill name columns still print, because the STS seed (external/sts-helpers) has
# them in its code. industries.csv uses the Operations Pro spelling (owner, 2026-11-25). The follow-up that renames
# those columns together with sts-helpers deletes this list.
OLD_SPELLINGS = {
    "A Stucki Co": "A. Stucki Co.",
    "Ferrel Gas": "Ferrellgas",
}


def _master_name(printed: str) -> str:
    return OLD_SPELLINGS.get(printed, printed)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _spots(label: str) -> set[int]:
    """1-3,5 -> {1, 2, 3, 5}; the same ranges waybill_deck._spots_from_label reads."""
    out: set[int] = set()
    for part in re.split(r"[,\s]+", label.strip()):
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        elif part:
            out.add(int(part))
    return out


class IndustryCopies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = {r["industry_id"]: r for r in _rows(DATA / "industries.csv")}
        cls.spots = _rows(DATA / "spot_assignments.csv")
        cls.waybills = _rows(DATA / "HART_Spot_Waybills.csv")
        cls.site = json.loads((ROOT / "www" / "data" / "industries.json").read_text(encoding="utf-8"))["industries"]

    def test_ids_and_slugs_are_lower_case_and_slugs_unique(self):
        for iid, row in self.master.items():
            self.assertRegex(iid, r"^[a-z][a-z0-9-]*$")
            self.assertRegex(row["slug"], r"^[a-z][a-z0-9-]*$")
        slugs = [r["slug"] for r in self.master.values()]
        self.assertEqual(len(slugs), len(set(slugs)), slugs)

    def test_spot_names_match_their_id(self):
        bad = [(r["industry_id"], r["Industry"]) for r in self.spots
               if self.master[r["industry_id"]]["name"] != _master_name(r["Industry"])]
        self.assertEqual(bad, [])

    def test_waybill_names_match_their_id(self):
        """Interchange traffic belongs to no industry: no id, INTERCHANGE on the card."""
        def ok(r: dict[str, str]) -> bool:
            if r["traffic"] == "interchange":
                return r["industry_id"] == "" and r["industry"] == INTERCHANGE_HEADER
            return self.master[r["industry_id"]]["name"] == _master_name(r["industry"])

        bad = [(r["card_id"], r["traffic"], r["industry_id"], r["industry"]) for r in self.waybills if not ok(r)]
        self.assertEqual(bad, [])

    def test_interchange_traffic_is_the_interchange_cards(self):
        self.assertEqual([r["card_id"] for r in self.waybills if r["traffic"] == "interchange"],
                         [r["card_id"] for r in self.waybills if r["card_kind"] == "interchange"])

    def test_waybill_spots_are_spots_of_their_industry(self):
        have = {(r["industry_id"], int(r["Spot #"])) for r in self.spots}
        bad = [(r["card_id"], r["industry_id"], n) for r in self.waybills
               if r["card_kind"] in ("loaded", "inbound_empty")
               for n in sorted(_spots(r["spots"])) if (r["industry_id"], n) not in have]
        self.assertEqual(bad, [])

    def test_site_lists_each_industry_once_under_its_public_name_and_slug(self):
        """Every entry is an industry of the master, or the one interchange entry, which has no id."""
        industries = [e for e in self.site if e.get("category") != "interchange"]
        self.assertEqual(sorted(e.get("industry_id") for e in industries), sorted(self.master))
        self.assertEqual([e.get("industry_id") for e in self.site if e.get("category") == "interchange"], [None])
        for e in industries:
            row = self.master[e["industry_id"]]
            self.assertEqual((e["name"], e["spot"], e["blurb"]), (row["public_name"], row["slug"], row["blurb"]),
                             e["industry_id"])

    def test_site_counts_and_commodities_follow_the_waybills(self):
        for e in self.site:
            if e.get("category") == "interchange":
                cards = [r for r in self.waybills if r["traffic"] == "interchange"]
            else:
                cards = [r for r in self.waybills if r["industry_id"] == e["industry_id"]]
            self.assertEqual(e["waybill_count"], len(cards), e["name"])
            if cards:  # an industry with no waybills (Shenango) lists its commodities by hand
                loads = sorted({r["commodity"] for r in cards if r["commodity"] != "EMPTY"})
                self.assertEqual(e["commodities"], loads, e["name"])


if __name__ == "__main__":
    unittest.main()
