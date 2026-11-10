"""Stage 3 gate, locomotive cards, public gallery, and the repo paths."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import cars  # noqa: E402
import intake_stages as st  # noqa: E402
import locos  # noqa: E402
import publish_gate as gate  # noqa: E402
import site_gallery as site  # noqa: E402


class PathTests(unittest.TestCase):
    def test_hart_root_is_the_repo_root(self):
        for module in (st, site, locos, cars):
            self.assertTrue((module.HART_ROOT / "wiki").is_dir(), module.__name__)


class GateTests(unittest.TestCase):
    def test_unfinished_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "b1").mkdir()
            st.write_csv(tmp / "b1/review.csv", st.REVIEW_COLUMNS, [
                {**{c: "" for c in st.REVIEW_COLUMNS}, "photo": "a.png", "status": s}
                for s in ("pending", "approved", "recorded", "rejected")
            ])
            self.assertEqual(gate.unfinished_batches(tmp),
                             ["b1/a.png is pending", "b1/a.png is approved"])
            self.assertEqual(gate.unfinished_batches(tmp / "none"), [])

    def test_backup_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.assertTrue(gate.backup_missing(tmp))
            (tmp / "dump.sql").write_text("x")
            self.assertEqual(gate.backup_missing(tmp), [])
            self.assertTrue(gate.backup_missing(tmp, now=time.time() + 13 * 3600))

    def test_pi_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in gate.OPS_FILES:
                (tmp / name).write_text(name)
            same = lambda *a, **k: SimpleNamespace(returncode=0, stdout=gate.ops_hash(tmp) + "\n", stderr="")
            other = lambda *a, **k: SimpleNamespace(returncode=0, stdout="abc\n", stderr="")
            down = lambda *a, **k: SimpleNamespace(returncode=255, stdout="", stderr="no route")
            self.assertEqual(gate.pi_out_of_step(tmp, "pi", "/x", run=same), [])
            self.assertIn("make ops-pull", gate.pi_out_of_step(tmp, "pi", "/x", run=other)[0])
            self.assertIn("could not read", gate.pi_out_of_step(tmp, "pi", "/x", run=down)[0])

    def test_uncommitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.csv"
            f.write_text("x")
            dirty = lambda *a, **k: SimpleNamespace(returncode=0, stdout=" M a.csv\n")
            clean = lambda *a, **k: SimpleNamespace(returncode=0, stdout="")
            self.assertEqual(gate.uncommitted([f], run=clean), [])
            self.assertEqual(gate.uncommitted([f], run=dirty), ["a.csv has uncommitted changes"])

    def test_only_skips_batch_and_commit_checks_but_not_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "b1").mkdir()
            st.write_csv(tmp / "b1/review.csv", st.REVIEW_COLUMNS,
                         [{**{c: "" for c in st.REVIEW_COLUMNS}, "photo": "a.png", "status": "pending"}])
            kw = dict(batch_root=tmp, tracked=[], ops_local=tmp, pi_host="pi", pi_dir="/x",
                      backups_dir=tmp / "none")
            full = gate.run_gate(only=False, skip=["pi"], **kw)
            self.assertTrue(any(p.startswith("[batches]") for p in full))
            one = gate.run_gate(only=True, skip=["pi"], **kw)
            self.assertEqual([p.split("]")[0] for p in one], ["[backup"])

    def test_unknown_skip_name(self):
        with self.assertRaises(SystemExit):
            gate.run_gate(batch_root=Path("."), tracked=[], ops_local=Path("."), pi_host="p",
                          pi_dir="/", backups_dir=Path("."), only=False, skip=["nope"])


class PublishOnlyTests(unittest.TestCase):
    def test_only_touches_the_chosen_car(self):
        import unittest.mock as mock

        queue = [{"roster_id": i, "reason": "new car", "queued": "d", "card_built": "",
                  "card_printed": "", "sts": "", "ops": ""} for i in ("A1", "B2")]
        written, sts_ids = [], []

        def fake_run(cmd, **kw):
            if "add_hart_cars.py" in cmd[1]:
                sts_ids.extend(cmd[2:])
            return SimpleNamespace(returncode=0)

        args = SimpleNamespace(only=["A1"], skip_check=[], ops_live="/nonexistent")
        with mock.patch.object(cars, "publish_gate"), \
             mock.patch("build_car_roster_sor.main"), \
             mock.patch.object(cars, "read_queue", return_value=queue), \
             mock.patch.object(cars, "write_queue", side_effect=lambda q: written.append([dict(x) for x in q])), \
             mock.patch.object(cars, "read_rows", return_value=([], [])), \
             mock.patch.object(cars, "merge_ops", return_value=["A1"]), \
             mock.patch.object(cars.shutil, "copy2"), \
             mock.patch.object(cars.subprocess, "run", side_effect=fake_run):
            cars.cmd_publish(args)
        self.assertEqual(sts_ids, ["A1"])
        final = {q["roster_id"]: q for q in written[-1]}
        self.assertTrue(final["A1"]["sts"] and final["A1"]["ops"])
        self.assertEqual((final["B2"]["sts"], final["B2"]["ops"]), ("", ""))
        self.assertEqual(len(final), 2)

    def test_unknown_id_refused(self):
        import unittest.mock as mock

        with mock.patch.object(cars, "publish_gate"), mock.patch("build_car_roster_sor.main"), \
             mock.patch.object(cars, "read_queue", return_value=[]):
            with self.assertRaises(SystemExit):
                cars.cmd_publish(SimpleNamespace(only=["ZZ9"], skip_check=[], ops_live="/x"))


class LocoCardTests(unittest.TestCase):
    def test_card_row_matches_an_existing_loco_card(self):
        import generate_all_cards as gen

        row = {"roster_id": "CWRY 2091", "road_name": "CWRY", "road_number": "2091",
               "source_image": "IMG_9192.png", "length_ft": "56", "model": "GP20",
               "loco_type": "Diesel", "mfg": ""}
        card, engine = locos.card_row(row)
        roster = gen.load_roster()
        _, engines = gen.load_engine_roster()
        record, _ = gen.row_to_card(card, roster, {**engines, ("CWRY", "2091"): engine})
        self.assertEqual((record["Type"], record["RoadName"], record["RoadNumber"]),
                         ("Locomotive", "Ohio Central", "2091"))
        self.assertIn("GP20", record["Description"])
        self.assertIn("56", record["Description"])


GALLERY = {"albums": [{"id": "locos", "count": 1}, {"id": "freight", "count": 1}, {"id": "mow", "count": 1}],
           "items": [
               {"album": "locos", "src": "../x/IMG_1.png", "type": "Locomotive"},
               {"album": "freight", "src": "../x/IMG_2.png", "type": "Boxcar"},
               {"album": "mow", "src": "../x/IMG_3.png", "type": "MOW"}]}


def record(kind, road="N&W", number="1"):
    return {"Type": kind, "RoadName": road, "RoadNumber": number, "Description": "d"}


class SiteTests(unittest.TestCase):
    def test_only_new_photographed_cars(self):
        data = json.loads(json.dumps(GALLERY))
        found = site.missing_entries([(record("Boxcar"), "IMG_2.png"), (record("MOW"), "IMG_9.png"),
                                      (record("Locomotive"), "IMG_8.png"), (record("Boxcar"), "")], data)
        self.assertEqual([(e["album"], e["src"].split("/")[-1]) for e in found],
                         [("mow", "IMG_9.png"), ("locos", "IMG_8.png")])
        self.assertEqual(found[0]["caption"], "N&W · MOW · d")

    def test_private_name_never_added(self):
        from test_intake_stages import stand_in_name

        with stand_in_name():
            found = site.missing_entries(
                [({**record("Boxcar"), "Description": "Blue Moon boxcar"}, "IMG_9.png")], GALLERY)
        self.assertEqual(found, [])

    def test_counts_recomputed(self):
        data = json.loads(json.dumps(GALLERY))
        site.add_entries(data, site.missing_entries([(record("Boxcar"), "IMG_9.png")], data))
        self.assertEqual({a["id"]: a["count"] for a in data["albums"]},
                         {"locos": 1, "freight": 2, "mow": 1})


if __name__ == "__main__":
    unittest.main()
