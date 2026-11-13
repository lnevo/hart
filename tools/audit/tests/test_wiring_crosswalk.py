"""check_wiring_crosswalk: heads in tables.xml must follow signal_wiring.csv."""
import csv
import importlib.util
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
SPEC = importlib.util.spec_from_file_location(
    "check_wiring_crosswalk", ROOT / "tools/audit/check_wiring_crosswalk.py"
)
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


def row(port, node, sig, name, mast, role):
    packed = name[2:]
    return {
        "port_id": port, "mqtt_node": node, "signal_index": sig,
        "uid": str(int(packed) - int(node) * 100), "packed": packed,
        "topic": f"track/signalhead/{packed}",
        "system_name": name, "mast_user_name": mast, "head_role": role,
    }


WIRING = [
    # Two-head mast, three lamps each.
    *[row(f"C2-OU1-{p}", "2", "0", "IH232", "Mast 24RA", "T") for p in (1, 2, 3)],
    *[row(f"C2-OU1-{p}", "2", "6", "IH238", "Mast 24RA", "B") for p in (4, 5, 6)],
    # Dwarf spread over two OUs.
    row("C12-OU2-7", "12", "2", "IH1234", "Mast 32R", "S"),
    row("C12-OU3-8", "12", "2", "IH1234", "Mast 32R", "S"),
    row("C12-OU3-7", "12", "2", "IH1234", "Mast 32R", "S"),
    # Interim mast: only the top head is on the mast.
    *[row(f"C4-OU2-{p}", "4", "0", "IH432", "Mast 6LB", "T") for p in (1, 2, 3)],
    *[row(f"C4-OU2-{p}", "4", "1", "IH433", "Mast 6LB", "B") for p in (4, 5, 6)],
]

COMMENTS = {
    "IH232": "Node: 2 Signal: 0 | OU: 1 Ports: 1,2,3",
    "IH238": "Node: 2 Signal: 6 | OU: 1 Ports: 4,5,6",
    "IH1234": "Node: 12 Signal: 2 | OU: 2 Ports: 7 | OU: 3 Ports: 8,7",
    "IH432": "Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3",
    "IH433": "Node: 4 Signal: 1 | OU: 2 Ports: 4,5,6",
}

MASTS = {
    "Mast 24RA": "IF$shsm:basic:two-searchlight(IH232)(IH238)",
    "Mast 32R": "IF$shsm:basic:one-low(IH1234)",
    "Mast 6LB": "IF$shsm:basic:one-low(IH432)",
    "Mast 1001": "IF$vsm:basic:one-low($1001)",
}


def tables(comments=COMMENTS, masts=MASTS) -> ET.Element:
    heads = "".join(
        f"<signalhead><systemName>{n}</systemName><comment>{c}</comment></signalhead>"
        for n, c in comments.items()
    )
    ms = "".join(
        f"<signalmast><systemName>{s}</systemName><userName>{u}</userName></signalmast>"
        for u, s in masts.items()
    )
    return ET.fromstring(
        f"<layout-config><signalheads>{heads}</signalheads>"
        f"<signalmasts>{ms}</signalmasts></layout-config>"
    )


class WiringCrosswalkTest(unittest.TestCase):
    def test_matching_tables_pass(self):
        self.assertEqual(check.problems(WIRING, tables()), [])

    def test_wrong_ih_number_on_mast_fails(self):
        masts = dict(MASTS, **{"Mast 24RA": "IF$shsm:basic:two-searchlight(IH1232)(IH1233)"})
        found = check.problems(WIRING, tables(masts=masts))
        self.assertIn("Mast 24RA: heads IH1232 IH1233, wiring plan IH232 IH238", found)

    def test_swapped_head_order_fails(self):
        masts = dict(MASTS, **{"Mast 24RA": "IF$shsm:basic:two-searchlight(IH238)(IH232)"})
        found = check.problems(WIRING, tables(masts=masts))
        self.assertTrue(any(f.startswith("Mast 24RA: heads") for f in found), found)

    def test_wired_head_on_no_mast_fails(self):
        masts = {k: v for k, v in MASTS.items() if k != "Mast 32R"}
        found = check.problems(WIRING, tables(masts=masts))
        self.assertIn("Mast 32R: wired mast missing from tables.xml", found)
        self.assertIn("IH1234 (Mast 32R S): wired head is on no mast", found)

    def test_undefined_wired_head_fails(self):
        comments = {k: v for k, v in COMMENTS.items() if k != "IH238"}
        found = check.problems(WIRING, tables(comments=comments))
        self.assertIn("IH238 (Mast 24RA B): wired head not defined in tables.xml", found)

    def test_unwired_head_mast_fails(self):
        masts = dict(MASTS, **{"Mast 99X": "IF$shsm:basic:one-low(IH999)"})
        found = check.problems(WIRING, tables(masts=masts))
        self.assertIn("Mast 99X: head mast IH999 is not in signal_wiring.csv", found)

    def test_comment_disagreeing_with_ports_fails(self):
        comments = dict(COMMENTS, IH232="Node: 12 Signal: 0 | OU: 2 Ports: 1,2,3")
        found = check.problems(WIRING, tables(comments=comments))
        self.assertTrue(any(f.startswith("IH232: comment") for f in found), found)

    def test_interim_mast_may_show_only_its_top_head(self):
        self.assertEqual(check.problems(WIRING, tables()), [])
        masts = dict(MASTS, **{"Mast 6LB": "IF$shsm:basic:one-low(IH433)"})
        found = check.problems(WIRING, tables(masts=masts))
        self.assertTrue(any(f.startswith("Mast 6LB: heads") for f in found), found)

    def test_head_mast_named_by_user_name_fails(self):
        masts = dict(MASTS, **{"Mast 99X": "IF$shsm:basic:one-low(Head 99X)"})
        found = check.problems(WIRING, tables(masts=masts))
        self.assertTrue(any(f.startswith("Mast 99X: head mast") for f in found), found)

    def test_duplicate_mast_user_name_fails(self):
        root = tables()
        dup = ET.SubElement(root.find("signalmasts"), "signalmast")
        ET.SubElement(dup, "systemName").text = "IF$shsm:basic:one-low(IH238)"
        ET.SubElement(dup, "userName").text = "Mast 24RA"
        found = check.problems(WIRING, root)
        self.assertIn("Mast 24RA: two head masts share this userName", found)

    def test_system_name_must_match_packed_and_topic(self):
        bad = [dict(r) for r in WIRING]
        bad[0]["system_name"] = "IH1232"
        with self.assertRaisesRegex(check.WiringError, "system_name IH1232 but packed 232"):
            check.problems(bad, tables())
        bad = [dict(r) for r in WIRING]
        bad[0]["topic"] = "track/signalhead/1241"
        with self.assertRaisesRegex(check.WiringError, "topic track/signalhead/1241"):
            check.problems(bad, tables())

    def test_packed_must_be_node_times_100_plus_uid(self):
        bad = [dict(r) for r in WIRING]
        bad[0]["uid"] = "33"
        with self.assertRaisesRegex(check.WiringError, "not node 2 x 100 \\+ uid 33"):
            check.problems(bad, tables())

    def test_bad_role_is_reported_not_a_traceback(self):
        bad = [dict(r) for r in WIRING]
        bad[0]["head_role"] = "M"
        with self.assertRaisesRegex(check.WiringError, "head_role 'M'"):
            check.problems(bad, tables())

    def test_repo_tables_follow_wiring_plan(self):
        with (ROOT / "docs/wiring/signals/signal_wiring.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        root = ET.parse(paths.TABLES_XML).getroot()
        self.assertEqual(check.problems(rows, root), [])


if __name__ == "__main__":
    unittest.main()
