"""bin/cars sync: dry run by default, identity fields only, every refusal before a write. Fakes only."""
import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import car_repo  # noqa: E402
import car_sync  # noqa: E402
from car_live_sts import LiveCar, LiveCars  # noqa: E402

ROW = {"roster_id": "NW2", "roster_road": "NW", "road_number": "2", "car_type": "Flatcar",
       "roster_length_ft": "52", "color": "Black", "notes": ""}
HEADER = '<?xml version="1.0" ?>\n<?xml-stylesheet href="x.xsl"?>\n'
OPS_OLD = HEADER + ('<operations-config><cars>'
                    '<car id="NW2" roadName="NW" roadNumber="2" type="Flatcar" length="50" color="Black" '
                    'locationId="9" moves="7" /></cars></operations-config>\n')
LIVE_URL = "http://sts.example.invalid/sts/api/v1"


class FakeApiError(RuntimeError):
    pass


class FakeApi:
    ApiError = FakeApiError

    def __init__(self, remarks="Flatcar 50ft", backup_fails=False, stale_readback=False, envelope=False):
        self.car = {"id": 11, "reporting_marks": "NW2", "remarks": remarks, "position": 5, "status": "Loaded"}
        self.backup_fails, self.stale_readback, self.envelope = backup_fails, stale_readback, envelope
        self.backups = Path(tempfile.mkdtemp())
        self.timeout_on_patch = False
        self.calls = []

    def post(self, path, body=None):
        self.calls.append(("POST", path, body))
        if self.backup_fails:
            raise FakeApiError("admin role needed")
        return {}

    def patch(self, path, body):
        self.calls.append(("PATCH", path, body))
        if self.timeout_on_patch:
            raise TimeoutError("timed out")
        if not self.stale_readback:
            self.car.update(body)
        return dict(self.car)

    def get(self, path):
        self.calls.append(("GET", path, None))
        return {"data": dict(self.car)} if self.envelope else dict(self.car)

    def backups_dir(self):
        return self.backups

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ops = self.tmp / "ops.xml"
        self.ops.write_text(OPS_OLD)
        self.gen = types.SimpleNamespace(PASSENGER_TYPES=set())
        self.api = FakeApi()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        env = self.stack.enter_context(unittest.mock.patch.dict(os.environ, {}))
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "read_rows", lambda: ([ROW], [])))
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "seed_helpers", lambda: (self.gen, None)))
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "SEED_INPUTS", self.tmp / "no-seed"))
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "OPS_MERGED", self.tmp / "ops.xml"))
        self.pi_problems = []
        self.stack.enter_context(
            unittest.mock.patch("publish_gate.pi_out_of_step", lambda *a, **k: list(self.pi_problems)))
        self.operating = None
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "operating_reason", lambda: self.operating))
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "load_sts_api", lambda: self.api))
        self.live = [dict(self.api.car)]
        self.stack.enter_context(unittest.mock.patch.object(
            car_sync, "fetch_live_cars",
            lambda: LiveCars(LIVE_URL, "live", [LiveCar.from_api(c, LIVE_URL) for c in self.live])))
        del env

    def run_sync(self, **kw):
        ns = dict(ops_live=str(self.ops), apply=False, live_sts=False, sts_url=None)
        ns.update(kw)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = car_sync.cmd_sync(types.SimpleNamespace(**ns))
        return rc, out.getvalue(), err.getvalue()

    def test_dry_run_lists_changes_and_writes_nothing(self):
        rc, out, _ = self.run_sync(live_sts=True, sts_url=LIVE_URL)
        self.assertEqual(rc, 0)
        self.assertIn("NW2 length: '50' -> '52'", out)
        self.assertIn("NW2 remarks: 'Flatcar 50ft' -> 'Flatcar 52ft'", out)
        self.assertIn("Dry run", out)
        self.assertEqual(self.ops.read_text(), OPS_OLD)
        self.assertEqual(self.api.writes(), [])

    def test_apply_edits_only_the_differing_attribute(self):
        rc, out, _ = self.run_sync(apply=True)
        self.assertEqual(rc, 0)
        text = self.ops.read_text()
        self.assertEqual(text, OPS_OLD.replace('length="50"', 'length="52"'))
        self.assertIn('locationId="9"', text)
        self.assertEqual(self.api.calls, [])

    def test_live_apply_updates_one_car_and_reads_it_back(self):
        self.ops.write_text(OPS_OLD.replace('length="50"', 'length="52"'))
        rc, out, _ = self.run_sync(apply=True, live_sts=True, sts_url=LIVE_URL)
        self.assertEqual(rc, 0, out)
        self.assertEqual([c[0] for c in self.api.writes()], ["POST", "PATCH"])
        self.assertEqual(self.api.writes()[0][1], "/admin/backups")
        self.assertEqual(self.api.writes()[1][1:], ("/cars/11", {"remarks": "Flatcar 52ft"}))
        self.assertEqual(self.api.calls[-1][:2], ("GET", "/cars/11"))
        self.assertEqual(self.api.car["position"], 5)
        self.assertIn("each read back", out)

    def test_live_apply_stops_when_the_read_back_differs(self):
        self.api.stale_readback = True
        rc, _, err = self.run_sync(apply=True, live_sts=True, sts_url=LIVE_URL)
        self.assertEqual(rc, 2)
        self.assertIn("sync stopped at car NW2", err)
        self.assertIn("read back", err)
        self.assertIn("written so far: none", err)

    def test_read_back_accepts_an_enveloped_body(self):
        self.api.envelope = True
        rc, out, _ = self.run_sync(apply=True, live_sts=True, sts_url=LIVE_URL)
        self.assertEqual(rc, 0, out)

    def test_a_timeout_stops_the_live_write_with_a_reason(self):
        self.api.timeout_on_patch = True
        rc, _, err = self.run_sync(apply=True, live_sts=True, sts_url=LIVE_URL)
        self.assertEqual(rc, 2)
        self.assertIn("sync stopped at car NW2: TimeoutError", err)

    def test_ops_live_other_than_the_repo_roster_is_refused(self):
        other = self.tmp / "other.xml"
        other.write_text(OPS_OLD)
        rc, _, err = self.run_sync(apply=True, ops_live=str(other))
        self.assertEqual(rc, 2)
        self.assertIn("only edits the repo roster", err)
        self.assertEqual(other.read_text(), OPS_OLD)

    def test_missing_seed_folder_refuses_before_the_ops_edit(self):
        seed = self.tmp / "seed"
        seed.mkdir()
        (seed / car_repo.MERGED.name).write_text(
            '<operations-config><cars><car id="NW2" roadName="NW" roadNumber="2" type="Flatcar" '
            'length="40" color="Black"/></cars></operations-config>')
        row = dict(ROW, notes="CarImagesFinal/x.png")
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "read_rows", lambda: ([row], [])))
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "SEED_INPUTS", seed))
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "METADATA", self.tmp / "absent.csv"))
        rc, _, err = self.run_sync(apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("Master file is missing", err)
        self.assertEqual(self.ops.read_text(), OPS_OLD)

    def test_operating_flag_refuses_before_any_write(self):
        self.operating = "owner is operating"
        rc, _, err = self.run_sync(apply=True, live_sts=True, sts_url=LIVE_URL)
        self.assertEqual(rc, 2)
        self.assertIn("operating flag", err)
        self.assertEqual(self.ops.read_text(), OPS_OLD)
        self.assertEqual(self.api.writes(), [])

    def test_no_backup_refuses_before_any_write(self):
        self.api.backup_fails = True
        rc, _, err = self.run_sync(apply=True, live_sts=True, sts_url=LIVE_URL)
        self.assertEqual(rc, 2)
        self.assertIn("backup", err)
        self.assertEqual(self.ops.read_text(), OPS_OLD)
        self.assertEqual([c[0] for c in self.api.writes()], ["POST"])

    def test_pi_files_that_differ_refuse_the_ops_edit(self):
        self.pi_problems = ["the Pi's Operations files differ from the repo copy"]
        rc, _, err = self.run_sync(apply=True)
        self.assertEqual(rc, 2)
        self.assertIn("differ from the repo copy", err)
        self.assertEqual(self.ops.read_text(), OPS_OLD)

    def test_live_apply_needs_an_explicit_url(self):
        rc, _, err = self.run_sync(apply=True, live_sts=True)
        self.assertEqual(rc, 2)
        self.assertIn("--sts-url", err)

    def test_nothing_to_do_when_everything_agrees(self):
        self.ops.write_text(OPS_OLD.replace('length="50"', 'length="52"'))
        self.live[0]["remarks"] = "Flatcar 52ft"
        rc, out, _ = self.run_sync(apply=True, live_sts=True, sts_url=LIVE_URL)
        self.assertEqual(rc, 0)
        self.assertIn("Nothing to do", out)
        self.assertEqual(self.api.calls, [])

    def test_seed_copies_are_refreshed_through_the_seed_copy_functions(self):
        seed = self.tmp / "seed"
        seed.mkdir()
        (seed / car_repo.MERGED.name).write_text(
            '<operations-config><cars><car id="NW2" roadName="NW" roadNumber="2" type="Flatcar" '
            'length="40" color="Black"/></cars></operations-config>')
        row = dict(ROW, notes="CarImagesFinal/x.png")
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "read_rows", lambda: ([row], [])))
        self.stack.enter_context(unittest.mock.patch.object(car_sync, "SEED_INPUTS", seed))
        self.ops.write_text(OPS_OLD.replace('length="50"', 'length="52"'))
        with unittest.mock.patch("build_car_roster_sor.main") as build, \
                unittest.mock.patch.object(car_sync, "sync_seed_copies") as copy:
            rc, out, _ = self.run_sync(apply=True)
        self.assertEqual(rc, 0, out)
        build.assert_called_once()
        copy.assert_called_once_with(seed, car_repo.SEED_COPIES)


if __name__ == "__main__":
    unittest.main()
