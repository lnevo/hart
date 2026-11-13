"""cs105_consist.py builds listener attach/detach payloads as OpenLCB does: 9 bytes."""
import pathlib
import re
import unittest

SRC = pathlib.Path(__file__).resolve().parents[1] / "cs105_consist.py"


def payload_builder():
    """Run the script's listener_payload() under Python 3 (it is plain Python)."""
    text = SRC.read_text()
    m = re.search(r"^def listener_payload\(.*?(?=^def )", text, re.S | re.M)
    assert m, "listener_payload() not found"
    ns = {}
    exec(m.group(0), ns)
    return ns["listener_payload"]


class PayloadTest(unittest.TestCase):
    def test_detach_has_flags_byte(self):
        p = payload_builder()(0x02, 0, "06.01.00.00.CA.B2")
        self.assertEqual(p, [0x30, 0x02, 0x00, 0x06, 0x01, 0x00, 0x00, 0xCA, 0xB2])

    def test_attach_carries_flags(self):
        p = payload_builder()(0x01, 6, "06.01.00.00.C8.49")
        self.assertEqual(p, [0x30, 0x01, 0x06, 0x06, 0x01, 0x00, 0x00, 0xC8, 0x49])

    def test_a_node_id_that_is_not_6_bytes_is_refused(self):
        with self.assertRaises(ValueError):
            payload_builder()(0x02, 0, "06.01.00.00.CA")

    def test_every_send_uses_the_builder(self):
        text = SRC.read_text()
        self.assertNotRegex(text, r"send\([^)]*\[0x30,\s*0x0[12]")

    def test_detach_drops_both_sides_and_queries_both(self):
        text = SRC.read_text()
        self.assertIn("((LEAD,FOLLOW),(FOLLOW,LEAD))", text)
        self.assertIn("for n in (LEAD,FOLLOW): query(n)", text)


if __name__ == "__main__":
    unittest.main()
