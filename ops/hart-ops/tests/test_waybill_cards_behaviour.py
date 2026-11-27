"""Behaviour tests for card_pipeline/generate_waybill_cards.py.

generate_operator_sheet imports norm, parse_spot_num, format_spots, load_spot_groups,
waybill_spec, inbound_commodity_label, SKIP_USAGES, SPOT_CSV, INDUSTRY_ORDER, BASE and EMPTY;
those are covered here.

Golden runs read a small frozen spot list (SPOT_CSV_TEXT below) and a stand-in sticker sheet,
with the random module seeded, so the snapshots do not depend on the live spot_assignments.csv,
the private sticker template or photos. The waybill rules (waybill_loads.csv, waybill_parties.csv,
waybill_empty_returns.csv) and the interchange rows of HART_Spot_Waybills.csv are read from the
repo's data files, so the snapshots follow them on purpose.
Golden data: tests/golden/w4c/waybills_*.
"""
import csv
import io
import random
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "card_pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from docx import Document  # noqa: E402

import car_paths  # noqa: E402
import generate_card_template as gct  # noqa: E402
import generate_waybill_cards as gwc  # noqa: E402
import waybill_data as wdata  # noqa: E402
import waybill_deck as wdeck  # noqa: E402
import waybill_sheet as wsheet  # noqa: E402
from golden_support import check_golden, docx_summary  # noqa: E402

TEST_ID = "test_waybill_cards_behaviour"
DEPENDS = ("the frozen spot list in test_waybill_cards_behaviour.py, a seeded random module, the waybill rule files "
           "in ops/hart-ops/data/ and the interchange rows of HART_Spot_Waybills.csv")
NO_FILE = Path("/nonexistent/w4c-fixture.png")

SPOT_CSV_TEXT = """Industry,Spot #,Usage,Cars Applicable
Calgon Carbon,1,Coal Unload,Loaded Hopper; Empty Hopper
Calgon Carbon,2,Coal Unload,Loaded Hopper; Empty Hopper
Calgon Carbon,3,Carbon Load,Covered Hopper
Calgon Carbon,4,Chemical Unload,Tank Car
Calgon Carbon,5,Off Spot,Tank Car
Ferrel Gas,1,LPG Unload,Tank Car
Test Works,7,Widget Unload,Boxcar
Test Works,8,Widget Shipping,Boxcar; Flatcar
Test Works,9,Siding,Gondola
Test Works,10,Storage,Gondola
,11,Widget Unload,Boxcar
Test Works,x,Widget Unload,Boxcar
Test Works,12,Widget Unload,
"""


def fake_sheet(path: Path) -> Path:
    doc = Document()
    doc.add_table(rows=3, cols=3)
    doc.save(path)
    return path


def read_rows(path: Path) -> list:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def spot_csv(tmp: Path, text: str = SPOT_CSV_TEXT) -> Path:
    path = tmp / "spots.csv"
    path.write_text(text, encoding="utf-8")
    return path


class SeededCase(unittest.TestCase):
    def seed(self, value):
        """Seed the global random module and put its state back after the test."""
        state = random.getstate()
        self.addCleanup(random.setstate, state)
        random.seed(value)


class Parsing(unittest.TestCase):
    def test_norm_strips_and_tolerates_none(self):
        self.assertEqual(wdata.norm("  a b "), "a b")
        self.assertEqual(wdata.norm(None), "")

    def test_parse_spot_num_keeps_digits_only(self):
        self.assertEqual(wdeck.parse_spot_num("Spot 12"), 12)
        self.assertEqual(wdeck.parse_spot_num("4a"), 4)
        self.assertEqual(wdeck.parse_spot_num(""), 0)
        self.assertEqual(wdeck.parse_spot_num("none"), 0)

    def test_normalize_car_type_folds_hopper_variants(self):
        for raw in ("Loaded Hopper", "empty hopper", "Coal Hopper", "Open Top Hopper Loaded"):
            self.assertEqual(wdeck.normalize_car_type(raw), "Hopper", raw)
        self.assertEqual(wdeck.normalize_car_type("Covered Hopper"), "Covered Hopper")
        self.assertEqual(wdeck.normalize_car_type("  Tank Car "), "Tank Car")

    def test_parse_car_types_dedupes_in_order_and_drops_blanks(self):
        self.assertEqual(
            wdeck.parse_car_types("Loaded Hopper; Empty Hopper; Tank Car;; Tank Car"),
            ("Hopper", "Tank Car"),
        )
        self.assertEqual(wdeck.parse_car_types(""), ())

    def test_format_spots_makes_ranges(self):
        self.assertEqual(wdeck.format_spots([3, 1, 2, 7, 9, 10, 2]), "1-3, 7, 9-10")
        self.assertEqual(wdeck.format_spots([5]), "5")
        self.assertEqual(wdeck.format_spots([0, 0]), "")
        self.assertEqual(wdeck.format_spots([]), "")

    def test_spots_from_label_round_trips_format_spots(self):
        self.assertEqual(wdeck._spots_from_label("1-3, 7, 9-10"), {1, 2, 3, 7, 9, 10})
        self.assertEqual(wdeck._spots_from_label(""), set())
        self.assertEqual(wdeck._spot_count("4-6"), 3)
        self.assertEqual(wdeck._spot_count(""), 1)

    def test_spots_from_label_rejects_garbage(self):
        with self.assertRaises(ValueError):
            wdeck._spots_from_label("one")

    def test_commodity_from_usage(self):
        cases = {
            "Coal Unload": "Coal", "Cement Unload": "Cement", "Aggregate Unload": "Aggregate",
            "LPG Unload": "LPG", "Pellet Load": "Plastic Pellets", "Chemical Unload": "Chemicals",
            "Carbon Load": "Activated Carbon", "Crane Spot": "Steel", "Shipping": "Plastic Resins",
        }
        for usage, expected in cases.items():
            self.assertEqual(wdeck._commodity_from_usage(usage), expected, usage)

    def test_usage_without_a_load_keyword_is_its_own_load_and_warns(self):
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err), mock.patch.object(wdeck, "_WARNED_USAGES", set()):
            self.assertEqual(wdeck._commodity_from_usage("Mystery", "Test Works"), "Mystery")
            self.assertEqual(wdeck._commodity_from_usage("Mystery", "Test Works"), "Mystery")
            wdeck._commodity_from_usage("Mystery", "Other Works")
        self.assertEqual(err.getvalue().count("'Mystery' at Test Works"), 1)
        self.assertEqual(err.getvalue().count("'Mystery' at Other Works"), 1)

    def test_party_pool_copies_do_not_share_the_table_parties(self):
        spec = wdata.spot_waybill()[("Calgon Carbon", "Coal Unload")]
        pool = wdeck.party_pool("IN", "Coal", spec)
        self.assertEqual(pool, spec["suppliers"])
        pool[0]["name"] = "changed"
        self.assertNotEqual(spec["suppliers"][0]["name"], "changed")


class SpotCsv(unittest.TestCase):
    def load(self, text=SPOT_CSV_TEXT):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(gwc, "SPOT_CSV", spot_csv(Path(tmp), text)):
                return gwc.load_spot_groups()

    def test_merges_spots_with_the_same_industry_usage_and_cars(self):
        groups = {(g["Industry"], g["Usage"]): g for g in self.load()}
        coal = groups[("Calgon Carbon", "Coal Unload")]
        self.assertEqual(coal["Spots"], "1-2")
        self.assertEqual(coal["CarTypes"], ("Hopper",))

    def test_skips_off_spot_storage_blank_and_unparseable_rows(self):
        usages = {(g["Industry"], g["Usage"]) for g in self.load()}
        self.assertNotIn(("Calgon Carbon", "Off Spot"), usages)
        self.assertNotIn(("Test Works", "Storage"), usages)
        self.assertEqual(
            sorted(u for i, u in usages if i == "Test Works"),
            ["Siding", "Widget Shipping", "Widget Unload"],
        )
        widget = [g for g in self.load() if g["Usage"] == "Widget Unload"]
        self.assertEqual(len(widget), 1)
        self.assertEqual(widget[0]["Spots"], "7")

    def test_missing_csv_raises_file_not_found_with_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            gone = Path(tmp) / "absent.csv"
            with mock.patch.object(gwc, "SPOT_CSV", gone):
                with self.assertRaises(FileNotFoundError) as cm:
                    gwc.load_spot_groups()
        self.assertIn("absent.csv", str(cm.exception))

    def test_header_only_csv_gives_no_groups(self):
        self.assertEqual(self.load("Industry,Spot #,Usage,Cars Applicable\n"), [])


class Specs(unittest.TestCase):
    def test_named_spec_wins(self):
        spec = wdeck.waybill_spec("Calgon Carbon", "Coal Unload")
        self.assertEqual(spec["inbound_load"], "Coal")
        self.assertEqual(wdeck.inbound_commodity_label(spec), "Coal")

    def test_unload_default(self):
        spec = wdeck.waybill_spec("Nowhere Inc", "Widget Unload")
        self.assertEqual(spec["inbound_load"], "Widget Unload")
        self.assertEqual(spec["outbound_load"], wdata.EMPTY)
        self.assertEqual(spec["suppliers"], [wdata.normalize_party("Various suppliers")])

    def test_load_default_is_an_empty_inbound(self):
        spec = wdeck.waybill_spec("Nowhere Inc", "Steel Load")
        self.assertEqual(spec["inbound_load"], wdata.EMPTY)
        self.assertEqual(spec["outbound_load"], "Steel")
        self.assertEqual(wdeck.inbound_commodity_label(spec), "Empty cars")

    def test_other_usage_is_general_freight(self):
        spec = wdeck.waybill_spec("Nowhere Inc", "Siding")
        self.assertEqual(spec["inbound_load"], "General Freight")
        self.assertEqual(spec["customers"], [
            {"name": "Various local receivers", "via": "CSX", "entry": "", "commodity": ""}])

    def test_normalize_party(self):
        self.assertEqual(
            wdata.normalize_party(" Plain Name "),
            {"name": "Plain Name", "via": "", "entry": "", "commodity": ""},
        )
        self.assertEqual(
            wdata.normalize_party({"name": " X ", "via": "NS"}),
            {"name": "X", "via": "NS", "entry": "", "commodity": ""},
        )

    def test_party_with_an_unknown_field_is_refused(self):
        with self.assertRaises(wdata.WaybillDataError) as cm:
            wdata.normalize_party({"name": "X", "route": "NS"})
        self.assertIn("route", str(cm.exception))

    def test_spec_with_missing_or_blank_fields_is_refused(self):
        with self.assertRaises(wdata.WaybillDataError) as cm:
            wdata.normalize_spec({"inbound_load": "Coal", "suppliers": [], "customers": []}, "here")
        self.assertIn("here", str(cm.exception))
        with self.assertRaises(wdata.WaybillDataError):
            wdata.normalize_spec({"inbound_load": "", "outbound_load": "EMPTY",
                                  "suppliers": [], "customers": []}, "here")

    def test_every_table_party_has_all_fields(self):
        for key, spec in wdata.spot_waybill().items():
            for party in spec["suppliers"] + spec["customers"]:
                self.assertEqual(set(party), {"name", "via", "entry", "commodity"}, key)

    def test_party_pool_picks_customers_for_empty_in_and_nothing_for_empty_out(self):
        spec = wdata.normalize_spec({"inbound_load": "Coal", "outbound_load": wdata.EMPTY,
                                     "suppliers": ["S"], "customers": [{"name": "C", "via": "CSX"}]}, "test")
        self.assertEqual([p["name"] for p in wdeck.party_pool("IN", wdata.EMPTY, spec)], ["C"])
        self.assertEqual(wdeck.party_pool("OUT", wdata.EMPTY, spec), [])
        self.assertEqual([p["name"] for p in wdeck.party_pool("IN", "Coal", spec)], ["S"])
        self.assertEqual([p["name"] for p in wdeck.party_pool("OUT", "Coal", spec)], ["C"])

    def test_apply_load_summary(self):
        card = {"Commodity": "Caustic Soda"}
        wdeck._apply_load_summary(card, "Process Chemicals")
        self.assertEqual(card["LoadSummary"], "Process Chemicals")
        card = {"Commodity": "Coal"}
        wdeck._apply_load_summary(card, "Coal")
        self.assertNotIn("LoadSummary", card)
        card = {"Commodity": "Coal"}
        wdeck._apply_load_summary(card, "Fuel")
        self.assertEqual(card["LoadSummary"], "Fuel")
        card = {"Commodity": "EMPTY"}
        wdeck._apply_load_summary(card, "Fuel")
        self.assertNotIn("LoadSummary", card)
        card = {"Commodity": "Coal", "LoadSummary": "kept"}
        wdeck._apply_load_summary(card, "Fuel")
        self.assertEqual(card["LoadSummary"], "kept")


class Routing(SeededCase):
    def party(self, **kw):
        return {"name": "N", "via": "", "entry": "", "commodity": "", **kw}

    def test_loaded_in_takes_the_party_name_and_entry_railroad(self):
        card = {}
        wdeck.apply_route(card, "IN", "Coal", self.party(entry="POHC"))
        self.assertEqual((card["RouteFrom"], card["RouteTo"], card["RouteChain"]), ("N", "", "POHC"))
        card = {}
        wdeck.apply_route(card, "IN", "Coal", self.party(entry="CSX"))
        self.assertEqual(card["RouteChain"], "CSX")

    def test_loaded_out_goes_to_the_customer_via_ns_or_pohc_as_pohc(self):
        for via, chain in (("NS", "POHC"), ("POHC", "POHC"), ("CSX", "CSX"), ("", "CSX")):
            card = {}
            wdeck.apply_route(card, "OUT", "Coal", self.party(via=via))
            self.assertEqual((card["RouteTo"], card["RouteChain"]), ("N", chain))

    def test_inbound_empty_only_sets_the_chain(self):
        card = {"Spots": "3", "RouteFrom": "x"}
        wdeck.apply_route(card, "IN", wdata.EMPTY, self.party(via="NS"))
        self.assertEqual((card["RouteFrom"], card["RouteTo"], card["RouteChain"]), ("", "", "POHC"))
        card = {"Spots": "3"}
        wdeck.apply_route(card, "IN", wdata.EMPTY, self.party())
        self.assertEqual(card["RouteChain"], "")

    def test_outbound_empty_card_keeps_its_return_route(self):
        card = {"CardKind": "outbound_empty", "RouteTo": "Yard", "RouteChain": "CSX"}
        wdeck.apply_route(card, "OUT", wdata.EMPTY, self.party())
        self.assertEqual((card["RouteTo"], card["RouteChain"]), ("Yard", "CSX"))

    def test_interchange_cards_are_untouched(self):
        card = {"CardKind": "interchange", "RouteFrom": "a"}
        wdeck.apply_route(card, "IN", "Coal", self.party())
        self.assertEqual(card, {"CardKind": "interchange", "RouteFrom": "a"})

    def test_spread_parties_edge_cases(self):
        blank = {"name": "", "via": "", "entry": "", "commodity": ""}
        self.assertEqual(wdeck.spread_parties([], 2), [blank, blank])
        self.assertEqual(wdeck.spread_parties([{"name": "A"}], 0), [])
        self.assertEqual(wdeck.spread_parties([{"name": "A"}], -3), [])
        self.seed(1)
        spread = wdeck.spread_parties([{"name": "A"}, {"name": "B"}], 3)
        self.assertEqual(len(spread), 3)
        self.assertEqual({p["name"] for p in spread}, {"A", "B"})
        picked = wdeck.spread_parties([{"name": "A"}, {"name": "B"}, {"name": "C"}], 2)
        self.assertEqual(len(picked), 2)

    def test_pad_designs(self):
        self.assertEqual(len(wdeck._pad_designs([{"a": 1}])), 3)
        self.assertEqual(len(wdeck._pad_designs([{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}])), 3)
        padded = wdeck._pad_designs([{"a": 1}, {"a": 2}])
        self.assertEqual([d["a"] for d in padded], [1, 2, 1])
        padded[0]["a"] = 99  # copies, not shared
        self.assertEqual(wdeck._pad_designs([{"a": 1}])[1]["a"], 1)


class DeckBuilding(SeededCase):
    def groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(gwc, "SPOT_CSV", spot_csv(Path(tmp))):
                return gwc.load_spot_groups()

    def test_card_kind(self):
        self.assertEqual(wdeck.card_kind({"CardKind": "interchange"}), "interchange")
        self.assertEqual(wdeck.card_kind({"Commodity": "EMPTY", "Spots": "1"}), "inbound_empty")
        self.assertEqual(wdeck.card_kind({"Commodity": "EMPTY"}), "outbound_empty")
        self.assertEqual(wdeck.card_kind({"Commodity": "Coal"}), "loaded")

    def test_deck_sort_puts_spot_cards_before_interchange_before_outbound_empties(self):
        deck = [
            {"Industry": "Calgon Carbon", "CardKind": "outbound_empty", "Commodity": "EMPTY"},
            {"Industry": "INTERCHANGE", "CardKind": "interchange", "Commodity": "Coal"},
            {"Industry": "Calgon Carbon", "Commodity": "Coal", "Spots": "1", "Flow": "OUT"},
            {"Industry": "Calgon Carbon", "Commodity": "Coal", "Spots": "1", "Flow": "IN"},
        ]
        kinds = [(c.get("Flow", ""), wdeck.card_kind(c)) for c in wdeck.sort_deck_by_industry(deck)]
        self.assertEqual(
            kinds,
            [("IN", "loaded"), ("OUT", "loaded"), ("", "interchange"), ("", "outbound_empty")],
        )

    def test_industry_counts_and_outbound_empties(self):
        groups = self.groups()
        counts = wdeck._industry_spot_counts(groups)
        self.assertEqual(counts["Calgon Carbon"], 4)
        self.assertEqual(wdeck._industry_inbound_empty_spots(groups)["Calgon Carbon"], {3})
        self.assertEqual(wdeck.industry_outbound_empty_counts(groups)["Calgon Carbon"], 3)
        cards = wdeck.build_industry_empty_cards(groups)
        calgon = [c for c in cards if c["Industry"] == "Calgon Carbon"]
        self.assertEqual(len(calgon), 3)
        self.assertEqual(calgon[0]["RouteTo"], "Scully Yard")
        self.assertEqual(calgon[0]["RouteChain"], "POHC")
        unknown = [c for c in cards if c["Industry"] == "Test Works"]
        self.assertEqual(unknown[0]["RouteTo"], "")

    def test_records_sorted_by_industry_then_spot_then_flow(self):
        records, order = wdeck.build_waybill_records(self.groups())
        self.assertEqual(order[0][0], "Calgon Carbon")
        self.assertEqual(order[-1][0], "Test Works")
        calgon = [r for r in records if r["Industry"] == "Calgon Carbon"]
        self.assertEqual(calgon[0]["Spots"], "1-2")
        self.assertEqual(calgon[0]["Flow"], "IN")

    def test_interchange_deck_is_the_master_rows(self):
        rows = wdata.interchange_rows()
        deck = wdeck.build_interchange_deck(rows)
        self.assertEqual(len(deck), len(rows))
        self.assertTrue(deck)
        for row, card in zip(rows, deck):
            self.assertEqual(card["CardKind"], "interchange")
            self.assertEqual(card["Industry"], wdata.INTERCHANGE_HEADER)
            self.assertEqual((card["Commodity"], card["CarType"], card["RouteFrom"], card["RouteTo"],
                              card["RouteChain"], card.get("LoadSummary", "")),
                             (row.commodity, row.car_type, row.route_from, row.route_to, row.via, row.load_summary))
            self.assertNotIn("Flow", card)   # interchange_flow counts in the report only; the card prints no flow

    def test_interchange_row_naming_an_island_industry_stops_the_build(self):
        row = wdata.interchange_rows()[0]._replace(route_to="Calgon Carbon")
        with self.assertRaises(wdata.WaybillDataError) as caught:
            wdeck.build_interchange_deck([row])
        self.assertIn(f"interchange card {row.card_id}", str(caught.exception))
        self.assertIn("Calgon Carbon", str(caught.exception))

    def test_a_broken_rule_file_is_a_card_pipeline_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "HART_Spot_Waybills.csv"
            with self.assertRaises(wdata.WaybillRulesFileError) as caught:
                wdata.interchange_rows(missing)
        self.assertIsInstance(caught.exception, car_paths.CardPipelineError)
        self.assertIn(str(missing), str(caught.exception))

    def test_is_layout_party(self):
        self.assertTrue(wdeck._is_layout_party("Aristech Plastics"))
        self.assertTrue(wdeck._is_layout_party(" Ferrellgas Co (Somewhere)"))
        self.assertFalse(wdeck._is_layout_party(""))
        self.assertFalse(wdeck._is_layout_party("Test Mill (Town, ME)"))

    def test_fill_deck_to_page_pads_to_a_full_sheet(self):
        self.seed(7)
        base = [
            {"Industry": "Calgon Carbon", "Commodity": "Coal", "Flow": "IN", "Usage": "Coal Unload",
             "Spots": "1", "CarType": "Hopper"},
            {"Industry": "Calgon Carbon", "Commodity": "EMPTY", "Flow": "OUT"},
        ]
        full = wsheet.fill_deck_to_page(list(base))
        self.assertEqual(len(full) % wsheet.CARDS_PER_PAGE, 0)
        self.assertEqual(len(full), 9)
        self.assertTrue(all(c["Commodity"] == "Coal" for c in full[2:]))
        exactly = [dict(base[0]) for _ in range(9)]
        self.assertEqual(len(wsheet.fill_deck_to_page(exactly)), 9)

    def test_fill_deck_to_page_names_a_filler_with_no_parties(self):
        self.seed(7)
        card = {"Industry": "Calgon Carbon", "Commodity": "Coal", "Flow": "IN", "Usage": "Coal Unload",
                "Spots": "1", "CarType": "Hopper"}
        spec = dict(wdeck.waybill_spec("Calgon Carbon", "Coal Unload"), suppliers=[])
        with mock.patch.object(wsheet, "waybill_spec", return_value=spec):
            with self.assertRaises(wsheet.EmptyPartyPoolError) as caught:
                wsheet.fill_deck_to_page([card])
        self.assertIsInstance(caught.exception, car_paths.CardPipelineError)
        self.assertIn("Calgon Carbon 'Coal Unload' (IN Coal)", str(caught.exception))
        self.assertIn("no suppliers", str(caught.exception))

    def test_fill_deck_to_page_copies_an_outbound_empty_with_a_blank_party(self):
        self.seed(7)
        card = {"Industry": "Calgon Carbon", "Commodity": "EMPTY", "Flow": "OUT", "Usage": "Coal Unload",
                "Spots": "1", "CarType": "Hopper", "RouteTo": "Somewhere", "RouteChain": "CSX"}
        full = wsheet.fill_deck_to_page([card])
        self.assertEqual(len(full), wsheet.CARDS_PER_PAGE)
        self.assertEqual({(c["RouteTo"], c["RouteChain"]) for c in full[1:]}, {("", "")})

    def test_summarize_deck(self):
        rows = wdeck.summarize_deck([
            {"Industry": "Calgon Carbon", "Commodity": "Coal", "Flow": "IN", "Spots": "1",
             "RouteChain": "CSX", "CarType": "Hopper", "Usage": "Coal Unload"},
            {"Industry": "Calgon Carbon", "Commodity": "EMPTY", "Flow": "OUT"},
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cards"], 2)
        self.assertEqual(rows[0]["commodities"], "Coal")
        self.assertEqual(rows[0]["vias"], "CSX")
        self.assertEqual(wdeck.summarize_deck([{"Industry": "X", "Commodity": "EMPTY"}])[0]["flows"], "—")

    def test_csv_export_writes_one_row_per_card_with_ids(self):
        deck = [{"Industry": "A", "Commodity": "Coal", "RouteChain": "CSX", "Flow": "IN"},
                {"Industry": "B", "Commodity": "EMPTY"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "w.csv"
            wdeck.export_waybill_csv(deck, path)
            rows = read_rows(path)
        self.assertEqual([r["card_id"] for r in rows], ["1", "2"])
        self.assertEqual(rows[0]["via"], "CSX")
        self.assertEqual(rows[0]["card_kind"], "loaded")
        self.assertEqual(rows[1]["card_kind"], "outbound_empty")


class MainRun(SeededCase):
    def run_main(self, tmp: Path, csv_text: str = SPOT_CSV_TEXT):
        sheet = fake_sheet(tmp / "sheet.docx")
        out_dir = tmp / "out"
        out_dir.mkdir()
        out = out_dir / "waybills.docx"
        csv_out = out_dir / "waybills.csv"
        self.seed(20260101)
        buf = io.StringIO()
        with mock.patch.object(car_paths, "STICKER_SHEET", sheet), \
                mock.patch.object(car_paths, "require_sticker_sheet", lambda: sheet), \
                mock.patch.multiple(gct, LOGO=NO_FILE, ICON_ROAD_NAME=NO_FILE,
                                    ICON_ROAD_NUM=NO_FILE, ICON_DESC=NO_FILE), \
                mock.patch.object(gwc, "SPOT_CSV", spot_csv(tmp, csv_text)), \
                mock.patch.object(gwc, "BASE", tmp), \
                mock.patch.object(gwc, "OUTPUT_DIR", out_dir), \
                mock.patch.object(gwc, "OUTPUT", out), \
                mock.patch.object(gwc, "WAYBILL_CSV", csv_out), \
                mock.patch("sys.stdout", buf):
            gwc.main()
        return out, csv_out, buf.getvalue()

    def normalise(self, text: str, tmp: Path) -> str:
        return text.replace(str(tmp), "<tmp>")

    def test_golden_csv_report_and_docx(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out, csv_out, stdout = self.run_main(tmp)
            csv_text = csv_out.read_text(encoding="utf-8")
            summary = docx_summary(Document(out).element.body)
            report = self.normalise(stdout, tmp)
        check_golden(self, "waybills_cards.csv", csv_text, depends_on=DEPENDS, test_id=TEST_ID)
        check_golden(self, "waybills_report.txt", report, depends_on=DEPENDS, test_id=TEST_ID)
        check_golden(self, "waybills_docx.txt", summary, depends_on=DEPENDS, test_id=TEST_ID)

    def test_deck_is_whole_pages_and_the_scratch_file_is_cleaned_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out, csv_out, _ = self.run_main(tmp)
            rows = read_rows(csv_out)
            doc = Document(out)
            self.assertFalse((tmp / ".scratch_waybill.docx").exists())
            self.assertFalse(out.with_suffix(".tmp.docx").exists())
        self.assertGreater(len(rows), 0)
        # the CSV is written before page fillers, so the sheet count is at least the CSV count
        self.assertGreaterEqual(len(doc.tables) * 9, len(rows))
        self.assertEqual(len(doc.tables), -(-len(rows) // 9))

    def test_main_with_no_usable_spots_still_writes_interchange_and_empties(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out, csv_out, _ = self.run_main(tmp, "Industry,Spot #,Usage,Cars Applicable\n")
            rows = read_rows(csv_out)
        self.assertTrue(rows)
        self.assertEqual({r["card_kind"] for r in rows}, {"interchange"})

    def test_main_fails_loudly_on_a_missing_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with mock.patch.object(gwc, "SPOT_CSV", tmp / "gone.csv"), \
                    mock.patch.object(gwc, "BASE", tmp), \
                    mock.patch.object(gwc, "OUTPUT_DIR", tmp), \
                    mock.patch.object(gwc, "OUTPUT", tmp / "w.docx"), \
                    mock.patch.object(gwc, "WAYBILL_CSV", tmp / "w.csv"):
                with self.assertRaises(FileNotFoundError):
                    gwc.main()
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
