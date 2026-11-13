"""Tests for the programming-on-the-main guard (speedmatch/pom_guard.py) and its Jython writer.

In-process only: a fake roster in a temp folder, consist query logs as text, a fake
programmer that records calls, and a stand-in `jmri` module for pom_write.py. No hardware,
no MQTT, no network.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEEDMATCH = HERE.parent / "speedmatch"
GUARD_PATH = SPEEDMATCH / "pom_guard.py"
WRITER_PATH = SPEEDMATCH / "pom_write.py"

spec = importlib.util.spec_from_file_location("pom_guard", GUARD_PATH)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

N2121 = "06.01.00.00.C8.49"
N2738 = "06.01.00.00.CA.B2"
TABLE_2738 = [12, 27, 50, 73, 94, 115, 135, 146, 155, 165, 174, 179, 184, 190] + [191] * 14


def long_cvs(addr, extra=None):
    cvs = {1: 3, 17: 0xC0 | (addr >> 8), 18: addr & 0xFF, 19: 0, 29: 50, 3: 26, 4: 24,
           25: 16, 66: 128, 95: 128}
    for k, v in enumerate(TABLE_2738, start=67):
        cvs[k] = v
    cvs.update(extra or {})
    return cvs


def loco_xml(rid, fname, number, long_flag, cvs, attr_number=None, protocol=None):
    proto = protocol or ("dcc_long" if long_flag == "yes" else "dcc_short")
    vals = "".join('<CVvalue name="%d" value="%d" />' % (k, v) for k, v in sorted(cvs.items()))
    return ('<locomotive id="%s" fileName="%s" dccAddress="%s">'
            '<locoaddress><dcclocoaddress number="%s" longaddress="%s" />'
            '<number>%s</number><protocol>%s</protocol></locoaddress>'
            '<values><decoderDef>%s</decoderDef></values></locomotive>') % (
        rid, fname, attr_number or number, number, long_flag, number, proto, vals)


DEFAULT = [
    ("CSX 2121", "2121.xml", 2121, "yes", long_cvs(2121)),
    ("CSX 2738", "2738.xml", 2738, "yes", long_cvs(2738)),
    ("NWR 06", "060.xml", 6, "yes", long_cvs(6)),
]


def make_roster(root, entries=DEFAULT, file_overrides=None):
    """Write roster.xml and roster/<file> like JMRI does. file_overrides: {fname: xml body}."""
    os.makedirs(os.path.join(root, "roster"), exist_ok=True)
    index = []
    for rid, fname, number, flag, cvs in entries:
        body = loco_xml(rid, fname, number, flag, {})
        index.append(body)
        fbody = (file_overrides or {}).get(fname) or loco_xml(rid, fname, number, flag, cvs)
        with open(os.path.join(root, "roster", fname), "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE locomotive-config SYSTEM "/xml/DTD/locomotive-config.dtd">\n'
                    "<locomotive-config>%s</locomotive-config>" % fbody)
    with open(os.path.join(root, "roster.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE roster-config SYSTEM "/xml/DTD/roster-config.dtd">\n'
                "<roster-config><roster>%s</roster></roster-config>" % "".join(index))
    return root


CLEAR = "%s listeners: 0\n%s listeners: 0\nEND\n" % (N2738, N2121)
CONSISTED = ("%s listeners: 0\n%s listeners: 1\n  raw payload: 30 03 01 00 06 06 01 00 00 CA B2\n"
             "  [0] flags 0x06 node %s\nEND\n") % (N2738, N2121, N2738)


def proposal(writes, rid="CSX 2738"):
    return {"roster_id": rid, "writes": [{"cv": c, "value": v} for c, v in writes]}


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def roster(self, entries=DEFAULT, file_overrides=None):
        sub = tempfile.mkdtemp(dir=self.dir)
        return g.load_roster(make_roster(sub, entries, file_overrides))

    def plan(self, writes, roster=None, log=CLEAR, partners=("CSX 2121",), rid="CSX 2738", reads=None):
        roster = roster if roster is not None else self.roster()
        state = g.parse_consist_log(log) if log is not None else None
        return g.build_plan(proposal(writes, rid), roster, state, partners=list(partners), reads=reads)

    def refused(self, fragment, fn, *a, **k):
        with self.assertRaises(g.GuardRefusal) as cm:
            fn(*a, **k)
        self.assertIn(fragment, str(cm.exception))


class AddressRefusals(GuardCase):
    def test_address_zero(self):
        self.refused("broadcast", g.check_address, 0, False)
        self.refused("broadcast", g.check_address, 0, True)
        r = self.roster(DEFAULT + [("ZERO", "0.xml", 0, "no", {})])
        self.refused("broadcast", self.plan, [(67, 1)], roster=r, rid="ZERO", partners=())

    def test_short_out_of_range(self):
        self.refused("outside 1-127", g.check_address, 128, False)
        r = self.roster(DEFAULT + [("BIG", "b.xml", 200, "no", {})])
        self.refused("short address 200", self.plan, [(67, 1)], roster=r, rid="BIG", partners=())

    def test_long_out_of_range(self):
        self.refused("outside 1-10239", g.check_address, 10240, True)
        g.check_address(10239, True)
        g.check_address(127, False)

    def test_flag_mismatch_between_index_and_file(self):
        bad = loco_xml("CSX 2738", "2738.xml", 2738, "no", long_cvs(2738))
        self.refused("roster.xml says 2738L", self.roster, file_overrides={"2738.xml": bad})

    def test_flag_mismatch_with_protocol(self):
        bad = loco_xml("CSX 2738", "2738.xml", 2738, "yes", long_cvs(2738), protocol="dcc_short")
        self.refused("protocol dcc_short", self.roster, file_overrides={"2738.xml": bad})

    def test_flag_mismatch_with_cv29(self):
        r = self.roster(DEFAULT[:1] + [("CSX 2738", "2738.xml", 2738, "yes", long_cvs(2738, {29: 18}))])
        self.refused("says short address", self.plan, [(67, 1)], roster=r)

    def test_cv17_cv18_must_encode_the_address(self):
        r = self.roster(DEFAULT[:1] + [("CSX 2738", "2738.xml", 2738, "yes", long_cvs(2738, {18: 1}))])
        self.refused("do not encode long address 2738", self.plan, [(67, 1)], roster=r)

    def test_shared_address(self):
        r = self.roster(DEFAULT + [("COPY 2738", "c.xml", 2738, "yes", long_cvs(2738))])
        self.refused("shares address 2738", self.plan, [(67, 1)], roster=r)

    def test_shared_number_across_flags_is_refused(self):
        r = self.roster(DEFAULT + [("SHORT 6", "s6.xml", 6, "no", {1: 6, 29: 2})])
        self.refused("shares address 6", self.plan, [(67, 1)], roster=r, rid="NWR 06", partners=())

    def test_unknown_roster_id(self):
        self.refused("not in the roster", self.plan, [(67, 1)], rid="CSX 9999")

    def test_target_in_advanced_consist(self):
        r = self.roster(DEFAULT[:1] + [("CSX 2738", "2738.xml", 2738, "yes", long_cvs(2738, {19: 20}))])
        self.refused("advanced consist", self.plan, [(67, 1)], roster=r)

    def test_short_target_that_is_a_consist_address(self):
        r = self.roster(DEFAULT + [("S20", "s20.xml", 20, "no", {1: 20, 29: 2}),
                                   ("S30", "s30.xml", 30, "no", {1: 30, 29: 2, 19: 20})])
        self.refused("CV19 consist address of 'S30'", self.plan, [(67, 1)], roster=r, rid="S20",
                     partners=(), log="06.01.00.00.00.14 listeners: 0\nEND\n")

    def test_train_node_matches_cs105(self):
        self.assertEqual(g.train_node(2121, True), N2121)
        self.assertEqual(g.train_node(2738, True), N2738)
        self.assertEqual(g.train_node(20, False), "06.01.00.00.00.14")


class ConsistRefusals(GuardCase):
    def test_consist_active(self):
        self.refused("break the consist first", self.plan, [(67, 1)], log=CONSISTED)

    def test_listener_seen_even_without_partner(self):
        self.refused("is a listener of", self.plan, [(67, 1)], log=CONSISTED, partners=())

    def test_query_missing(self):
        self.refused("no consist query result", self.plan, [(67, 1)], log=None)

    def test_query_failed(self):
        self.refused("consist query failed", self.plan, [(67, 1)], log="ERROR no memo\nEND\n")

    def test_query_incomplete(self):
        self.refused("incomplete", self.plan, [(67, 1)], log=CLEAR.replace("END\n", ""))

    def test_node_did_not_answer(self):
        log = "%s listeners: 0\n%s listeners: None\nEND\n" % (N2738, N2121)
        self.refused("did not answer", self.plan, [(67, 1)], log=log)

    def test_partner_not_queried(self):
        self.refused("did not cover train node %s" % N2121, self.plan, [(67, 1)],
                     log="%s listeners: 0\nEND\n" % N2738)

    def test_decode_error(self):
        log = CLEAR.replace("END", "  [0] decode error boom\nEND")
        self.refused("consist query failed", self.plan, [(67, 1)], log=log)

    def test_partners_must_be_given(self):
        state = g.parse_consist_log(CLEAR)
        self.refused("partners not given", g.build_plan, proposal([(67, 1)]), self.roster(), state, None)


class CvRefusals(GuardCase):
    def test_named_cvs(self):
        for cv, word in ((1, "short address"), (17, "long address"), (18, "long address"),
                         (19, "consist"), (8, "reset")):
            self.refused(word, self.plan, [(cv, 3)])

    def test_cv_not_in_list(self):
        for cv in (2, 5, 6, 7, 30, 96, 0, 1024):
            self.refused("not in the allowed list", self.plan, [(cv, 3)])

    def test_every_allowed_cv_passes(self):
        writes = [(cv, 10) for cv in sorted(g.ALLOWED_CVS) if cv != 29]
        plan = self.plan(writes)
        self.assertEqual(len(plan["rows"]), 33)

    def test_value_out_of_range(self):
        for v in (256, -1, "12", True, 12.0, None):
            self.refused("not an integer 0-255", self.plan, [(67, v)])

    def test_cv29_other_bit_change(self):
        self.refused("only bit 4", self.plan, [(29, 51)])
        self.refused("only bit 4", self.plan, [(29, 18)])  # would drop the long-address bit

    def test_cv29_bit4_change_is_allowed(self):
        row = self.plan([(29, 34)])["rows"][0]
        self.assertEqual((row["old"], row["new"], row["old_source"]), (50, 34, "roster"))

    def test_cv29_checked_against_the_read_value(self):
        self.refused("only bit 4", self.plan, [(29, 50)], reads={29: 34 | 1})

    def test_duplicate_cv(self):
        self.refused("twice", self.plan, [(67, 1), (67, 2)])

    def test_unknown_key_in_write(self):
        p = {"roster_id": "CSX 2738", "writes": [{"cv": 67, "value": 1, "vale": 2}]}
        self.refused("unknown keys", g.validate_proposal, p)

    def test_empty_writes(self):
        self.refused("no writes", g.validate_proposal, {"roster_id": "CSX 2738", "writes": []})

    def test_no_old_value_no_write(self):
        cvs = long_cvs(2738)
        del cvs[94]
        r = self.roster(DEFAULT[:1] + [("CSX 2738", "2738.xml", 2738, "yes", cvs)])
        self.refused("no rollback possible", self.plan, [(94, 1)], roster=r)


class FakeProgrammer:
    def __init__(self, fail_cv=None):
        self.calls = []
        self.fail_cv = fail_cv

    def write(self, cv, value):
        self.calls.append((cv, value))
        if cv == self.fail_cv:
            return False, "status 32 (No acknowledge)"
        return True, "status 0 (OK)"


class DryRunAndApply(GuardCase):
    def test_dry_run_prints_the_plan_and_writes_nothing(self):
        plan = self.plan([(67, 14), (29, 34), (3, 26)])
        lines, prog = [], FakeProgrammer()
        res = g.execute(plan, prog.write, log=lines.append)
        self.assertFalse(res["applied"])
        self.assertEqual(prog.calls, [])
        self.assertEqual(lines[0], "PLAN CSX 2738 address 2738L (long) train node %s" % N2738)
        self.assertIn("PLAN 2738L CV67 old=12 (roster) new=14", lines)
        self.assertIn("PLAN 2738L CV3 old=26 (roster) new=26 (same, skipped)", lines)
        self.assertTrue(lines[-1].startswith("DRY RUN"))

    def test_apply_flag_must_be_exactly_true(self):
        plan = self.plan([(67, 14)])
        prog = FakeProgrammer()
        rb = os.path.join(self.dir, "rb.json")
        for flag in (False, None, "yes", 1, "True"):
            self.assertFalse(g.execute(plan, prog.write, apply=flag, rollback_path=rb)["applied"])
        self.assertEqual(prog.calls, [])
        self.assertFalse(os.path.exists(rb))

    def test_apply_needs_a_rollback_path(self):
        self.refused("rollback file path", g.execute, self.plan([(67, 14)]), FakeProgrammer().write,
                     apply=True)

    def test_apply_writes_in_order_and_saves_rollback_first(self):
        plan = self.plan([(25, 16), (67, 14), (68, 27), (29, 34)], reads={67: 9})
        rb = os.path.join(self.dir, "rb.json")
        seen = []

        def write(cv, value):
            seen.append(os.path.exists(rb))
            return FakeProgrammer.write(prog, cv, value)
        prog = FakeProgrammer()
        res = g.execute(plan, write, apply=True, rollback_path=rb)
        self.assertTrue(all(seen))
        self.assertEqual(prog.calls, [(67, 14), (29, 34)])  # 25 and 68 already hold the value
        self.assertEqual(res["written"], [67, 29])
        doc = json.loads(Path(rb).read_text())
        self.assertEqual(doc["roster_id"], "CSX 2738")
        self.assertEqual(doc["old_values_from"], "mixed")
        self.assertEqual([(w["cv"], w["value"], w["old_source"]) for w in doc["writes"]],
                         [(25, 16, "roster"), (67, 9, "read"), (68, 27, "roster"), (29, 50, "roster")])
        # the rollback file is itself a proposal the guard accepts
        back = g.build_plan(doc, self.roster(), g.parse_consist_log(CLEAR), partners=["CSX 2121"])
        self.assertEqual([r["new"] for r in back["rows"]], [16, 9, 27, 50])

    def test_apply_stops_at_first_failure(self):
        plan = self.plan([(67, 14), (68, 30), (69, 51)])
        prog, lines = FakeProgrammer(fail_cv=68), []
        res = g.execute(plan, prog.write, apply=True, rollback_path=os.path.join(self.dir, "r.json"),
                        log=lines.append)
        self.assertEqual(prog.calls, [(67, 14), (68, 30)])
        self.assertEqual(res["failed"], 68)
        self.assertTrue(any(line.startswith("STOPPED at CV68") for line in lines))

    def test_apply_will_not_overwrite_a_rollback(self):
        rb = os.path.join(self.dir, "rb.json")
        Path(rb).write_text("{}")
        prog = FakeProgrammer()
        self.refused("already exists", g.execute, self.plan([(67, 14)]), prog.write,
                     apply=True, rollback_path=rb)
        self.assertEqual(prog.calls, [])

    def test_tampered_plan_is_caught_before_the_write(self):
        plan = self.plan([(67, 14), (68, 30)])
        plan["rows"][1]["cv"] = 17
        prog = FakeProgrammer()
        self.refused("CV17", g.execute, plan, prog.write, apply=True,
                     rollback_path=os.path.join(self.dir, "r.json"))
        self.assertEqual(prog.calls, [(67, 14)])


# ---------------------------------------------------------------- pom_write.py with a fake jmri

class _Listener:
    OK, NoAck = 0, 0x20

    def programmingOpReply(self, value, status):  # overridden by the script's subclass
        pass


class _Prog:
    def __init__(self, number, is_long, log):
        self.number, self.is_long, self.log = number, is_long, log

    def getAddressNumber(self):
        return self.number

    def getLongAddress(self):
        return self.is_long

    def getAddress(self):
        return "%d%s" % (self.number, "L" if self.is_long else "S")

    def decodeErrorCode(self, s):
        return "OK" if s == 0 else "No acknowledge"

    def readCV(self, cv, listener):
        self.log.append(("read", cv))
        listener.programmingOpReply(0, _Listener.NoAck)  # no RailCom: reads fail

    def writeCV(self, cv, value, listener):
        self.log.append(("write", cv, value))
        listener.programmingOpReply(value, _Listener.OK)


def fake_jmri(roster_dir, calls, roster_number=2738):
    jmri = types.ModuleType("jmri")
    jmri.ProgListener = _Listener

    class AddressedProgrammerManager:
        pass

    class OlcbProgrammerManager(AddressedProgrammerManager):
        def getAddressedProgrammer(self, is_long, number):
            calls.append(("programmer", is_long, number))
            return _Prog(number, is_long, calls)

    class Memo:
        def get(self, cls):
            return OlcbProgrammerManager() if cls is AddressedProgrammerManager else None

    class Entry:
        def getDccAddress(self):
            return str(roster_number)

        def isLongAddress(self):
            return True

    class Roster:
        @staticmethod
        def getDefault():
            return Roster()

        def getEntryForId(self, rid):
            return Entry() if rid == "CSX 2738" else None

        def getRosterLocation(self):
            return roster_dir + os.sep

    class InstanceManager:
        @staticmethod
        def getNullableDefault(cls):
            return Memo()

    jmri.AddressedProgrammerManager = AddressedProgrammerManager
    jmri.InstanceManager = InstanceManager
    jmri.jmrix = types.SimpleNamespace(can=types.SimpleNamespace(CanSystemConnectionMemo=object),
                                       openlcb=types.SimpleNamespace(OlcbProgrammerManager=OlcbProgrammerManager))
    jmri.jmrit = types.SimpleNamespace(roster=types.SimpleNamespace(Roster=Roster))
    return jmri


class PomWriteScript(GuardCase):
    def run_writer(self, apply, consist_log=CLEAR, guard_path=None, roster_number=2738, partners=("CSX 2121",)):
        roster_dir = make_roster(os.path.join(self.dir, "u"))
        prop = os.path.join(self.dir, "proposal.json")
        Path(prop).write_text(json.dumps(proposal([(67, 14), (29, 34)])))
        fake_query = os.path.join(self.dir, "fake_consist.py")
        with open(fake_query, "w") as f:
            f.write("with open(LOGF, 'w') as q:\n    q.write(%r)\nRESULT = 'started'\n" % consist_log)
        logf = os.path.join(self.dir, "pom.log")
        rb = os.path.join(self.dir, "rollback.json")
        calls = []
        env = {"__name__": "pom_write_test", "PROPOSAL": prop, "GUARD_PATH": guard_path or str(GUARD_PATH),
               "CONSIST_SCRIPT": fake_query, "PARTNERS": list(partners) if partners is not None else None,
               "LOGF": logf, "ROLLBACK": rb, "APPLY": apply, "RUN_INLINE": True,
               "OP_TIMEOUT": 1.0, "CONSIST_TIMEOUT": 2.0,
               "execfile": lambda path, e: exec(Path(path).read_text(), e)}
        if partners is None:
            del env["PARTNERS"]
        with mock.patch.dict(sys.modules, {"jmri": fake_jmri(roster_dir, calls, roster_number)}):
            exec(compile(WRITER_PATH.read_text(), str(WRITER_PATH), "exec"), env)
        return Path(logf).read_text().splitlines(), calls, rb

    def test_dry_run_reads_but_does_not_write(self):
        lines, calls, rb = self.run_writer(apply=False)
        self.assertIn(("programmer", True, 2738), calls)
        self.assertFalse([c for c in calls if c[0] == "write"])
        self.assertIn("PLAN 2738L CV67 old=12 (roster) new=14", lines)
        self.assertTrue(any(line.startswith("DRY RUN") for line in lines))
        self.assertFalse(os.path.exists(rb))
        self.assertEqual(lines[-1], "END")

    def test_apply_writes_through_the_addressed_programmer(self):
        lines, calls, rb = self.run_writer(apply=True)
        self.assertEqual([c for c in calls if c[0] == "write"], [("write", "67", 14), ("write", "29", 34)])
        self.assertTrue(os.path.exists(rb))
        self.assertIn("DONE 2 write(s)", lines)

    def test_consist_present_refuses_before_any_programmer(self):
        lines, calls, _ = self.run_writer(apply=True, consist_log=CONSISTED)
        self.assertEqual(calls, [])
        self.assertTrue(any(line.startswith("REFUSED") and "consist" in line for line in lines))

    def test_missing_guard_refuses(self):
        lines, calls, _ = self.run_writer(apply=True, guard_path=os.path.join(self.dir, "nope.py"))
        self.assertEqual(calls, [])
        self.assertTrue(lines[0].startswith("REFUSED guard module could not be loaded"))

    def test_jmri_roster_disagreeing_with_file_refuses(self):
        lines, calls, _ = self.run_writer(apply=True, roster_number=2739)
        self.assertEqual(calls, [])
        self.assertTrue(any("disagrees with roster file" in line for line in lines))

    def test_partners_must_be_set(self):
        lines, calls, _ = self.run_writer(apply=True, partners=None)
        self.assertEqual(calls, [])
        self.assertTrue(any("PARTNERS is not set" in line for line in lines))


class Jython27Syntax(unittest.TestCase):
    """The guard and writer run in Jython 2.7: keep Python-3-only syntax out."""

    def test_no_py3_only_syntax(self):
        import re
        for path in (GUARD_PATH, WRITER_PATH):
            src = path.read_text()
            self.assertNotRegex(src, r"(?m)^\s*from __future__ import [^\n]*print_function", path.name)
            self.assertIsNone(re.search(r"""\bf["']""", src), "%s has an f-string" % path.name)
            self.assertIsNone(re.search(r"(?m)^\s*(nonlocal|async |await )", src), path.name)
            self.assertIsNone(re.search(r"(?m)def \w+\([^)]*:\s*\w", src), "%s has type hints" % path.name)
            self.assertIsNone(re.search(r"(?m)^\s*def .*\)\s*->", src), "%s has a return annotation" % path.name)
            self.assertNotIn("print(", src, path.name)


if __name__ == "__main__":
    unittest.main()
