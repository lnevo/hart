"""compare --live-sts: GET only, same rules as the seed sections, no network."""
import contextlib
import io
import json
import sys
import unittest
import unittest.mock
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import cars  # noqa: E402

ROW = {"roster_id": "NW2", "roster_road": "NW", "road_number": "2", "car_type": "Flatcar",
       "roster_length_ft": "52", "color": "Black", "notes": ""}


class LiveStsTests(unittest.TestCase):
    def setUp(self):
        gen, reason = cars.seed_helpers()
        if gen is None or not (cars.STS_HELPERS / "lib/sts_api.py").is_file():
            self.skipTest(reason or "sts-helpers lib missing")
        self.requests = []

    def fake_urlopen(self, body=None, error=None):
        def opener(req, timeout=None, **kw):
            self.requests.append((req.get_method(), req.full_url, timeout))
            if error:
                raise error
            path = req.full_url.split("/api/v1", 1)[1].split("?")[0]
            data, meta = ({"stack": "live"}, {}) if path == "/health" else (body, {"total": len(body)})

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def read(self):
                    return json.dumps({"data": data, "meta": meta}).encode()

            return Resp()

        return unittest.mock.patch("urllib.request.urlopen", opener)

    def run_section(self, body=None, error=None, operating=lambda: None):
        out = io.StringIO()
        env = {"STS_API_URL": "http://sts.example.invalid/sts/api/v1", "STS_API_TOKEN": "x"}
        with unittest.mock.patch.dict("os.environ", env), self.fake_urlopen(body, error), \
                contextlib.redirect_stdout(out):
            rc = cars.print_live_sts([ROW], False, operating=operating)
        return rc, out.getvalue()

    def test_match_reports_no_differences_and_only_gets(self):
        rc, out = self.run_section([{"reporting_marks": "NW2", "remarks": "Flatcar 52ft"}])
        self.assertEqual(rc, 0)
        self.assertIn("Field differences: 0", out)
        self.assertIn("Target: live", out)
        self.assertTrue(self.requests and all(m == "GET" for m, _, _ in self.requests))
        self.assertTrue(all(t == cars.LIVE_STS_TIMEOUT for _, _, t in self.requests))

    def test_difference_is_reported_and_position_is_ignored(self):
        live = [{"reporting_marks": "NW2", "remarks": "Flatcar 50ft", "position": 9, "status": "Loaded"},
                {"reporting_marks": "XX9", "remarks": "Boxcar 40ft"}]
        rc, out = self.run_section(live)
        self.assertEqual(rc, 0)
        self.assertIn("NW2 remarks: repo='Flatcar 52ft' tool='Flatcar 50ft'", out)
        self.assertIn("Field differences: 1", out)
        self.assertIn("not in the repository: XX9", out)

    def test_unreachable_says_so_without_a_traceback_or_fallback(self):
        rc, out = self.run_section(error=urllib.error.URLError("timed out"))
        self.assertEqual(rc, 2)
        self.assertIn("cannot reach STS at http://sts.example.invalid/sts/api/v1", out)
        self.assertNotIn("Field differences", out)

    def test_operating_flag_refuses_before_any_request(self):
        rc, out = self.run_section([], operating=lambda: "speed matching")
        self.assertEqual(rc, 2)
        self.assertIn("operating flag is set (speed matching)", out)
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
