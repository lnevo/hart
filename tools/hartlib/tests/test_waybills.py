"""hartlib.waybills: the waybill rule files and the interchange rows of the card master, and their error paths."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "src"))

from hartlib import waybills  # noqa: E402
from hartlib.errors import HartlibError  # noqa: E402

LOADS = "industry_id,usage,inbound_load,outbound_load\n"
PARTIES = "industry_id,usage,role,party,name,via,entry,commodity\n"
RETURNS = "industry_id,route_to,via\n"
MASTER = ",".join(waybills.INTERCHANGE_COLUMNS) + "\n"
IX_ROW = "{id},interchange,interchange,{flow},Coal,,Hopper,A (Town),B (Town),CSX\n"


class Files(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def loads(self, rows: str = "calgon,Coal Unload,Coal,EMPTY\n") -> Path:
        return self.write("loads.csv", LOADS + rows)

    def raises(self, pattern: str, fn, *args):
        with self.assertRaisesRegex(waybills.WaybillRulesError, pattern) as caught:
            fn(*args)
        self.assertIsInstance(caught.exception, HartlibError)
        self.assertIsInstance(caught.exception, ValueError)


class SpotRules(Files):
    def test_parties_in_party_order_whatever_the_row_order(self):
        parties = self.write("p.csv", PARTIES + "calgon,Coal Unload,supplier,2,B,,POHC,\n"
                                                "calgon,Coal Unload,supplier,1,A,,,\n"
                                                "calgon,Coal Unload,customer,1,C,NS,,Slag\n")
        rule = waybills.read_spot_rules(self.loads(), parties)[("calgon", "Coal Unload")]
        self.assertEqual((rule.inbound_load, rule.outbound_load), ("Coal", "EMPTY"))
        self.assertEqual([p.name for p in rule.suppliers], ["A", "B"])
        self.assertEqual(rule.suppliers[1].entry, "POHC")
        self.assertEqual(rule.customers, (waybills.RuleParty("C", "NS", "", "Slag"),))

    def test_a_usage_with_no_parties_has_empty_lists(self):
        rule = waybills.read_spot_rules(self.loads(), self.write("p.csv", PARTIES))[("calgon", "Coal Unload")]
        self.assertEqual((rule.suppliers, rule.customers), ((), ()))

    def test_missing_file(self):
        self.raises("cannot read it", waybills.read_spot_rules, self.dir / "none.csv", self.dir / "p.csv")
        self.raises("none.csv: cannot read it", waybills.read_spot_rules, self.loads(), self.dir / "none.csv")

    def test_missing_column(self):
        self.raises("no column outbound_load", waybills.read_loads,
                    self.write("l.csv", "industry_id,usage,inbound_load\ncalgon,Coal Unload,Coal\n"))
        self.raises("no column party", waybills.read_spot_rules, self.loads(),
                    self.write("p.csv", "industry_id,usage,role,name,via,entry,commodity\n"))

    def test_bad_key(self):
        self.raises("industry_id must not be empty", waybills.read_loads, self.loads(",Coal Unload,Coal,EMPTY\n"))
        for party in ("x", "0", "1.5", "²"):
            self.raises("party .* is not a whole number from 1", waybills.read_spot_rules, self.loads(),
                        self.write("p.csv", PARTIES + f"calgon,Coal Unload,supplier,{party},A,,,\n"))
        self.raises("role 'seller' is not one of supplier, customer", waybills.read_spot_rules, self.loads(),
                    self.write("p.csv", PARTIES + "calgon,Coal Unload,seller,1,A,,,\n"))

    def test_duplicate_key(self):
        self.raises(r"loads.csv:3: calgon 'Coal Unload' is listed twice", waybills.read_loads,
                    self.loads("calgon,Coal Unload,Coal,EMPTY\ncalgon,Coal Unload,Slag,EMPTY\n"))
        self.raises(r"p.csv:3: calgon 'Coal Unload' supplier 1 is listed twice", waybills.read_spot_rules,
                    self.loads(), self.write("p.csv", PARTIES + "calgon,Coal Unload,supplier,1,A,,,\n"
                                                                "calgon,Coal Unload,supplier,1,B,,,\n"))

    def test_a_party_needs_a_load_row_and_numbers_without_gaps(self):
        self.raises("kosmos 'Coal Unload' has no row in loads.csv", waybills.read_spot_rules, self.loads(),
                    self.write("p.csv", PARTIES + "kosmos,Coal Unload,supplier,1,A,,,\n"))
        self.raises(r"supplier parties are numbered \[1, 3\], not 1 to 2", waybills.read_spot_rules, self.loads(),
                    self.write("p.csv", PARTIES + "calgon,Coal Unload,supplier,1,A,,,\n"
                                                  "calgon,Coal Unload,supplier,3,B,,,\n"))

    def test_roads_outside_their_lists(self):
        self.raises("via 'BNSF' is not one of CSX, NS, POHC", waybills.read_spot_rules, self.loads(),
                    self.write("p.csv", PARTIES + "calgon,Coal Unload,customer,1,A,BNSF,,\n"))
        self.raises("entry 'NS' is not one of CSX, POHC", waybills.read_spot_rules, self.loads(),
                    self.write("p.csv", PARTIES + "calgon,Coal Unload,supplier,1,A,,NS,\n"))
        self.raises("name must not be empty", waybills.read_spot_rules, self.loads(),
                    self.write("p.csv", PARTIES + "calgon,Coal Unload,supplier,1,,,,\n"))


class EmptyReturns(Files):
    def test_reads_by_industry(self):
        path = self.write("r.csv", RETURNS + "calgon,Scully Yard,POHC\nkosmos,Demmler Yard,CSX\n")
        self.assertEqual(waybills.read_empty_returns(path)["kosmos"],
                         waybills.EmptyReturn("kosmos", "Demmler Yard", "CSX"))

    def test_error_paths(self):
        self.raises("cannot read it", waybills.read_empty_returns, self.dir / "none.csv")
        self.raises("no column via", waybills.read_empty_returns, self.write("r.csv", "industry_id,route_to\n"))
        self.raises("industry_id must not be empty", waybills.read_empty_returns,
                    self.write("r.csv", RETURNS + ",Scully Yard,POHC\n"))
        self.raises("r.csv:3: calgon is listed twice", waybills.read_empty_returns,
                    self.write("r.csv", RETURNS + "calgon,Scully Yard,POHC\ncalgon,Demmler Yard,CSX\n"))
        self.raises("via 'NS' is not one of CSX, POHC", waybills.read_empty_returns,
                    self.write("r.csv", RETURNS + "calgon,Scully Yard,NS\n"))
        self.raises("route_to 'Glenwood Yard' is not one of Demmler Yard, Scully Yard", waybills.read_empty_returns,
                    self.write("r.csv", RETURNS + "calgon,Glenwood Yard,POHC\n"))

    def test_the_yards_are_the_sidecars(self):
        sidecar = waybills.WAYBILL_EMPTY_RETURNS.with_name("waybill_empty_returns.columns.csv")
        with sidecar.open(newline="", encoding="utf-8") as f:
            values = {r["column"]: r["values"] for r in csv.DictReader(f)}
        self.assertEqual(tuple(values["route_to"].split(";")), waybills.RETURN_YARDS)


class Interchange(Files):
    def test_interchange_rows_only_in_card_id_order(self):
        path = self.write("m.csv", MASTER + IX_ROW.format(id=9, flow="OUT")
                          + "3,industry,loaded,,Coal,,Hopper,A,,CSX\n" + IX_ROW.format(id=4, flow="IN"))
        cards = waybills.read_interchange(path)
        self.assertEqual([(c.card_id, c.flow) for c in cards], [(4, "IN"), (9, "OUT")])
        self.assertEqual(cards[0], waybills.InterchangeCard(4, "IN", "Coal", "", "Hopper", "A (Town)", "B (Town)",
                                                            "CSX"))

    def test_missing_file_and_column(self):
        self.raises("cannot read it", waybills.read_interchange, self.dir / "none.csv")
        self.raises("no column interchange_flow", waybills.read_interchange,
                    self.write("m.csv", MASTER.replace("interchange_flow,", "")))

    def test_bad_and_duplicate_card_id(self):
        self.raises("card_id 'x' is not a whole number", waybills.read_interchange,
                    self.write("m.csv", MASTER + IX_ROW.format(id="x", flow="IN")))
        self.raises("m.csv:3: card_id 4 is listed twice", waybills.read_interchange,
                    self.write("m.csv", MASTER + "4,industry,loaded,,Coal,,Hopper,A,,CSX\n"
                               + IX_ROW.format(id=4, flow="IN")))

    def test_row_shape(self):
        self.raises("interchange_flow 'UP' is not one of IN, OUT", waybills.read_interchange,
                    self.write("m.csv", MASTER + IX_ROW.format(id=1, flow="UP")))
        self.raises("interchange_flow must not be empty", waybills.read_interchange,
                    self.write("m.csv", MASTER + IX_ROW.format(id=1, flow="")))
        self.raises("interchange traffic with card_kind 'loaded'", waybills.read_interchange,
                    self.write("m.csv", MASTER + IX_ROW.format(id=1, flow="IN").replace(
                        "interchange,interchange", "interchange,loaded")))
        self.raises("interchange_flow is for interchange traffic only", waybills.read_interchange,
                    self.write("m.csv", MASTER + "3,industry,loaded,IN,Coal,,Hopper,A,,CSX\n"))


def _master_rows() -> list[dict[str, str]]:
    with waybills.SPOT_WAYBILLS.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class TheRepoFiles(unittest.TestCase):
    """The repo's own files read, and the master's industry cards agree with the rules they were built from."""

    def test_they_read(self):
        rules = waybills.read_spot_rules()
        self.assertIn(("calgon", "Coal Unload"), rules)
        self.assertTrue(waybills.read_empty_returns())
        cards = waybills.read_interchange()
        self.assertTrue(cards)
        self.assertEqual([c.card_id for c in cards], sorted(c.card_id for c in cards))

    def test_outbound_empty_cards_carry_their_industrys_return(self):
        returns = waybills.read_empty_returns()
        for row in _master_rows():
            if row["card_kind"] == "outbound_empty":
                r = returns[row["industry_id"]]
                self.assertEqual((row["route_to"], row["via"]), (r.route_to, r.via), row["card_id"])

    def test_loaded_cards_name_a_party_of_their_rule(self):
        rules = waybills.read_spot_rules()
        for row in _master_rows():
            if row["card_kind"] != "loaded":
                continue
            rule = rules[(row["industry_id"], row["usage"])]
            pool = rule.suppliers if row["flow"] == "IN" else rule.customers
            party = row["route_from"] if row["flow"] == "IN" else row["route_to"]
            self.assertIn(party, [p.name for p in pool], row["card_id"])


if __name__ == "__main__":
    unittest.main()
