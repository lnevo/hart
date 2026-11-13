"""Tests for the programming-on-the-main guard (speedmatch/pom_guard.py) and its Jython writer.

In-process only: a fake roster in a temp folder, consist query logs as text, a fake
programmer that records calls, and a stand-in `jmri` module for pom_write.py. No hardware,
no MQTT, no network.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stdout
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
N06 = "06.01.00.00.C0.06"
N572 = "06.01.00.00.C2.3C"
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
    rid_attr = 'id="%s" ' % rid if rid is not None else ""
    return ('<locomotive %sfileName="%s" dccAddress="%s">'
            '<locoaddress><dcclocoaddress number="%s" longaddress="%s" />'
            '<number>%s</number><protocol>%s</protocol></locoaddress>'
            '<values><decoderDef>%s</decoderDef></values></locomotive>') % (
        rid_attr, fname, attr_number or number, number, long_flag, number, proto, vals)


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
        index.append(loco_xml(rid, fname, number, flag, {}))
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


def qlog(answers, end=True):
    """A cs105_consist query log. answers: {node: None | [listener nodes]}."""
    out = []
    for node, lst in answers.items():
        if lst is None:
            out.append("%s listeners: None" % node)
            continue
        out.append("%s listeners: %d" % (node, len(lst)))
        for i, ln in enumerate(lst):
            out.append("  raw payload: 30 03 %02X %02X 06 .." % (len(lst), i))
            out.append("  [%d] flags 0x06 node %s" % (i, ln))
    if end:
        out.append("END")
    return "\n".join(out) + "\n"


CLEAR = qlog({N2738: [], N2121: [], N06: []})
CONSISTED = qlog({N2738: [], N2121: [N2738], N06: []})


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

    def plan(self, writes, roster=None, log=CLEAR, rid="CSX 2738", reads=None, absent_ok=(),
             reads_file=None, ledger=None):
        roster = roster if roster is not None else self.roster()
        if log == "auto":
            log = qlog(dict((n, []) for _, n in g.query_nodes(roster, rid)))
        state = g.parse_consist_log(log) if log is not None else None
        return g.build_plan(proposal(writes, rid), roster, state, absent_ok=absent_ok, reads=reads,
                            reads_file=reads_file, ledger=ledger)

    def refused(self, fragment, fn, *a, **k):
        with self.assertRaises(g.GuardRefusal) as cm:
            fn(*a, **k)
        self.assertIn(fragment, str(cm.exception))


class AddressRefusals(GuardCase):
    def test_address_zero(self):
        self.refused("broadcast", g.check_address, 0, False)
        self.refused("broadcast", g.check_address, 0, True)
        r = self.roster(DEFAULT + [("ZERO", "0.xml", 0, "no", {})])
        self.refused("broadcast", self.plan, [(67, 1)], roster=r, rid="ZERO")

    def test_short_out_of_range(self):
        self.refused("outside 1-127", g.check_address, 128, False)
        r = self.roster(DEFAULT + [("BIG", "b.xml", 200, "no", {})])
        self.refused("short address 200", self.plan, [(67, 1)], roster=r, rid="BIG")

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
        self.refused("shares address 6", self.plan, [(67, 1)], roster=r, rid="NWR 06")

    def test_unknown_roster_id(self):
        self.refused("not in the roster", self.plan, [(67, 1)], rid="CSX 9999")

    def test_roster_entry_without_id(self):
        self.refused("locomotive with no id", self.roster, DEFAULT + [(None, "x.xml", 99, "yes", {})])

    def test_target_in_advanced_consist(self):
        r = self.roster(DEFAULT[:1] + [("CSX 2738", "2738.xml", 2738, "yes", long_cvs(2738, {19: 20}))])
        self.refused("advanced consist", self.plan, [(67, 1)], roster=r)

    def test_short_target_that_is_a_consist_address(self):
        r = self.roster(DEFAULT + [("S20", "s20.xml", 20, "no", {1: 20, 29: 2}),
                                   ("S30", "s30.xml", 30, "no", {1: 30, 29: 2, 19: 20})])
        self.refused("CV19 consist address of 'S30'", self.plan, [(67, 1)], roster=r, rid="S20", log="auto")

    def test_train_node_matches_cs105(self):
        self.assertEqual(g.train_node(2121, True), N2121)
        self.assertEqual(g.train_node(2738, True), N2738)
        self.assertEqual(g.train_node(572, True), N572)
        self.assertEqual(g.train_node(20, False), "06.01.00.00.00.14")


class ConsistRefusals(GuardCase):
    def test_query_nodes_is_every_roster_entry_target_first(self):
        nodes = g.query_nodes(self.roster(), "CSX 2738")
        self.assertEqual(nodes, [("CSX 2738", N2738), ("CSX 2121", N2121), ("NWR 06", N06)])

    def test_consist_active(self):
        self.refused("is a listener of", self.plan, [(67, 1)], log=CONSISTED)

    def test_target_with_listeners(self):
        self.refused("has listener(s)", self.plan, [(67, 1)], rid="CSX 2121", log=CONSISTED)

    def test_follower_of_a_lead_nobody_named_is_caught(self):
        r = self.roster(DEFAULT + [("BO 572", "5720.xml", 572, "yes", long_cvs(572))])
        log = qlog({N2738: [], N2121: [], N06: [], N572: [N2738]})
        self.refused("listener of train node %s" % N572, self.plan, [(67, 1)], roster=r, log=log)

    def test_other_consists_do_not_block(self):
        r = self.roster(DEFAULT + [("BO 572", "5720.xml", 572, "yes", long_cvs(572))])
        log = qlog({N2738: [], N2121: [N06], N06: [], N572: []})
        self.assertEqual(len(self.plan([(67, 1)], roster=r, log=log)["rows"]), 1)

    def test_every_roster_node_must_be_queried(self):
        self.refused("did not cover 'NWR 06'", self.plan, [(67, 1)], log=qlog({N2738: [], N2121: []}))

    def test_query_missing(self):
        self.refused("no consist query result", self.plan, [(67, 1)], log=None)

    def test_query_failed(self):
        self.refused("consist query failed", self.plan, [(67, 1)], log="ERROR no memo\nEND\n")

    def test_query_incomplete(self):
        self.refused("incomplete", self.plan, [(67, 1)], log=qlog({N2738: [], N2121: [], N06: []}, end=False))

    def test_decode_error(self):
        self.refused("consist query failed", self.plan, [(67, 1)],
                     log=CLEAR.replace("END", "  [0] decode error boom\nEND"))

    def test_absent_node_refused(self):
        log = qlog({N2738: [], N2121: [], N06: None})
        self.refused("'NWR 06' (train node %s) did not answer" % N06, self.plan, [(67, 1)], log=log)

    def test_absent_ok_allows_and_logs(self):
        log = qlog({N2738: [], N2121: [], N06: None})
        plan = self.plan([(67, 1)], log=log, absent_ok=["NWR 06"])
        self.assertEqual(plan["notes"], ["ABSENT_OK 'NWR 06' train node %s did not answer" % N06])
        self.assertIn(plan["notes"][0], g.plan_lines(plan))

    def test_target_must_answer_even_if_absent_ok(self):
        log = qlog({N2738: None, N2121: [], N06: []})
        self.refused("did not answer", self.plan, [(67, 1)], log=log)
        self.refused("cannot be in ABSENT_OK", self.plan, [(67, 1)], log=log, absent_ok=["CSX 2738"])

    def test_listener_count_mismatch_is_unknown(self):
        log = CLEAR.replace("%s listeners: 0" % N2121, "%s listeners: 1" % N2121)
        self.refused("state unknown", self.plan, [(67, 1)], log=log)


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
        self.assertEqual(len(self.plan(writes)["rows"]), 33)

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

    def test_cv29_checked_against_the_ledger(self):
        led = {"roster_id": "CSX 2738", "cvs": {"29": {"value": 51, "state": "sent", "t": 1.0}}}
        self.refused("only bit 4", self.plan, [(29, 34)], ledger=led)

    def test_duplicate_cv(self):
        self.refused("twice", self.plan, [(67, 1), (67, 2)])

    def test_unknown_key_in_write(self):
        p = {"roster_id": "CSX 2738", "writes": [{"cv": 67, "value": 1, "vale": 2}]}
        self.refused("unknown keys", g.validate_proposal, p)

    def test_extra_top_level_keys_are_ignored(self):
        p = proposal([(67, 1)])
        p.update({"round": 2, "source": "propose_table", "anchors": [1, 2]})
        self.assertEqual(g.validate_proposal(p), ("CSX 2738", [(67, 1)]))

    def test_empty_writes(self):
        self.refused("no writes", g.validate_proposal, {"roster_id": "CSX 2738", "writes": []})

    def test_no_old_value_no_write(self):
        cvs = long_cvs(2738)
        del cvs[94]
        r = self.roster(DEFAULT[:1] + [("CSX 2738", "2738.xml", 2738, "yes", cvs)] + DEFAULT[2:])
        self.refused("no rollback possible", self.plan, [(94, 1)], roster=r)

    def test_bad_reads_values(self):
        for bad in ({67: 256}, {67: -1}, {67: "12"}, {67: True}, {67: 1.5}, {"x": 1}, {True: 1}, [1]):
            self.refused("", g.validate_reads, bad)
        self.assertEqual(g.validate_reads({"67": 12, 68: 0}), {67: 12, 68: 0})
        self.refused("not an integer 0-255", self.plan, [(67, 1)], reads={67: 300})

    def test_cli_bad_reads_file_is_a_refusal_not_a_traceback(self):
        d = make_roster(os.path.join(self.dir, "u"))
        prop, rd, cl = (os.path.join(self.dir, n) for n in ("p.json", "r.json", "c.log"))
        Path(prop).write_text(json.dumps(proposal([(67, 14)])))
        Path(rd).write_text(json.dumps({"67": 999}))
        Path(cl).write_text(CLEAR)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = g._main([prop, "--roster-dir", d, "--consist-log", cl, "--reads", rd])
        self.assertEqual(rc, 2)
        self.assertIn("REFUSED reads CV67 value 999", out.getvalue())
        Path(rd).write_text(json.dumps({"67": 12}))
        out = io.StringIO()
        with redirect_stdout(out):
            rc = g._main([prop, "--roster-dir", d, "--consist-log", cl, "--reads", rd])
        self.assertEqual(rc, 0)
        self.assertIn("PLAN 2738L CV67 old=12 (read) new=14", out.getvalue())


class OldValues(GuardCase):
    def test_precedence_read_then_reads_file_then_ledger_then_roster(self):
        led = {"roster_id": "CSX 2738", "cvs": {"67": {"value": 20, "state": "sent", "t": 100.0}}}
        row = lambda **k: self.plan([(67, 30)], **k)["rows"][0]
        self.assertEqual((row()["old"], row()["old_source"]), (12, "roster"))
        r = row(ledger=led)
        self.assertEqual((r["old"], r["old_source"]), (20, "ledger"))
        r = row(ledger=led, reads_file=(50.0, {67: 15}))  # older than the ledger entry
        self.assertEqual((r["old"], r["old_source"]), (20, "ledger"))
        r = row(ledger=led, reads_file=(200.0, {67: 15}))  # newer
        self.assertEqual((r["old"], r["old_source"]), (15, "reads_file"))
        r = row(ledger=led, reads_file=(200.0, {67: 15}), reads={67: 17})
        self.assertEqual((r["old"], r["old_source"]), (17, "read"))

    def test_no_skip_unless_read_this_run(self):
        led = {"roster_id": "CSX 2738", "cvs": {"68": {"value": 40, "state": "sent", "t": 1.0}}}
        plan = self.plan([(3, 26), (68, 40), (69, 50)], ledger=led, reads_file=(9e9, {69: 50}))
        self.assertEqual([r["skip"] for r in plan["rows"]], [False, False, False])
        prog = FakeProgrammer()
        g.execute(plan, prog.write, apply=True, rollback_path=os.path.join(self.dir, "rb.json"),
                  ledger=led, ledger_file=os.path.join(self.dir, "led.json"))
        self.assertEqual(prog.calls, [(3, 26), (68, 40), (69, 50)])
        plan = self.plan([(3, 26)], reads={3: 26})
        self.assertTrue(plan["rows"][0]["skip"])

    def test_ledger_precedence_across_two_rounds(self):
        lf = os.path.join(self.dir, "ledger", "CSX_2738.json")
        led = g.load_ledger(lf, "CSX 2738")
        prog = FakeProgrammer()
        g.execute(self.plan([(67, 14), (68, 30)], ledger=led), prog.write, apply=True,
                  rollback_path=os.path.join(self.dir, "rb1.json"), ledger=led, ledger_file=lf)
        led2 = g.load_ledger(lf, "CSX 2738")
        self.assertEqual(led2["cvs"]["67"]["value"], 14)
        self.assertEqual(led2["cvs"]["67"]["state"], "sent")
        plan2 = self.plan([(67, 16), (68, 30)], ledger=led2)
        self.assertEqual([(r["old"], r["old_source"]) for r in plan2["rows"]], [(14, "ledger"), (30, "ledger")])
        rb2 = os.path.join(self.dir, "rb2.json")
        g.execute(plan2, prog.write, apply=True, rollback_path=rb2, ledger=led2, ledger_file=lf)
        doc = json.loads(Path(rb2).read_text())
        self.assertEqual([(w["cv"], w["value"], w["old_source"]) for w in doc["writes"]],
                         [(67, 14, "ledger"), (68, 30, "ledger")])
        # round 2 wrote 68 again: the ledger value was not trusted for a skip
        self.assertEqual(prog.calls, [(67, 14), (68, 30), (67, 16), (68, 30)])

    def test_timeout_marks_unknown_and_next_run_refuses(self):
        lf = os.path.join(self.dir, "led.json")
        led = g.load_ledger(lf, "CSX 2738")
        prog, lines = FakeProgrammer(timeout_cv=68), []
        res = g.execute(self.plan([(67, 14), (68, 30), (69, 51)], ledger=led), prog.write, apply=True,
                        rollback_path=os.path.join(self.dir, "rb.json"), ledger=led, ledger_file=lf,
                        log=lines.append)
        self.assertTrue(res["timed_out"])
        self.assertEqual(prog.calls, [(67, 14), (68, 30)])
        self.assertTrue(any("may have been written" in line for line in lines))
        self.assertTrue(lines[-1].startswith("STOPPED: CV68 timed out"))
        led2 = g.load_ledger(lf, "CSX 2738")
        self.assertEqual(led2["cvs"]["68"]["state"], "unknown")
        self.refused("CV68 is unknown in the ledger", self.plan, [(68, 31)], ledger=led2)
        self.plan([(67, 15)], ledger=led2)  # other CVs still plan
        self.assertEqual(self.plan([(68, 31)], ledger=led2, reads={68: 30})["rows"][0]["old_source"], "read")
        newer = led2["cvs"]["68"]["t"] + 1
        self.assertEqual(self.plan([(68, 31)], ledger=led2, reads_file=(newer, {68: 30}))["rows"][0]
                         ["old_source"], "reads_file")
        g.clear_ledger(lf, ["68"])
        self.assertEqual(self.plan([(68, 31)], ledger=g.load_ledger(lf, "CSX 2738"))["rows"][0]["old_source"],
                         "roster")

    def test_failed_write_also_marks_unknown(self):
        lf = os.path.join(self.dir, "led.json")
        led = g.load_ledger(lf, "CSX 2738")
        res = g.execute(self.plan([(67, 14), (68, 30)]), FakeProgrammer(fail_cv=67).write, apply=True,
                        rollback_path=os.path.join(self.dir, "rb.json"), ledger=led, ledger_file=lf)
        self.assertEqual(res["failed"], 67)
        self.assertEqual(g.load_ledger(lf, "CSX 2738")["cvs"]["67"]["state"], "unknown")

    def test_reads_file_for_another_loco_is_refused(self):
        p = os.path.join(self.dir, "r.json")
        g.save_reads(p, {"number": 2121, "long": True}, "CSX 2121", {67: 1})
        self.refused("not this loco", g.load_reads_file, p, "CSX 2738", 2738, True)
        t, reads = g.load_reads_file(p, "CSX 2121", 2121, True)
        self.assertEqual(reads, {67: 1})

    def test_ledger_for_another_loco_is_refused(self):
        lf = os.path.join(self.dir, "led.json")
        Path(lf).write_text(json.dumps({"roster_id": "CSX 2121", "cvs": {}}))
        self.refused("not 'CSX 2738'", g.load_ledger, lf, "CSX 2738")


class FakeProgrammer:
    def __init__(self, fail_cv=None, timeout_cv=None):
        self.calls = []
        self.fail_cv = fail_cv
        self.timeout_cv = timeout_cv

    def write(self, cv, value):
        self.calls.append((cv, value))
        if cv == self.fail_cv:
            return "failed", "status 32 (No acknowledge)"
        if cv == self.timeout_cv:
            return "timeout", "timeout after 10s"
        return "ok", "status 0 (OK)"


class DryRunAndApply(GuardCase):
    def ledger(self):
        lf = os.path.join(self.dir, "led.json")
        return {"ledger": g.load_ledger(lf, "CSX 2738"), "ledger_file": lf}

    def test_dry_run_prints_the_plan_and_writes_nothing(self):
        plan = self.plan([(67, 14), (29, 34), (3, 26)])
        lines, prog = [], FakeProgrammer()
        rb = os.path.join(self.dir, "rb.json")
        res = g.execute(plan, prog.write, rollback_path=rb, log=lines.append)
        self.assertFalse(res["applied"])
        self.assertEqual(prog.calls, [])
        self.assertEqual(lines[0], "PLAN CSX 2738 address 2738L (long) train node %s" % N2738)
        self.assertIn("PLAN 2738L CV67 old=12 (roster) new=14", lines)
        self.assertIn("PLAN 2738L CV3 old=26 (roster) new=26", lines)
        self.assertTrue(lines[-1].startswith("DRY RUN"))
        self.assertFalse(os.path.exists(rb))
        self.assertEqual(json.loads(Path(rb + ".dryrun").read_text())["writes"][0], {"cv": 67, "value": 12, "old_source": "roster"})

    def test_apply_flag_must_be_exactly_true(self):
        plan = self.plan([(67, 14)])
        prog = FakeProgrammer()
        rb = os.path.join(self.dir, "rb.json")
        for flag in (False, None, "yes", 1, "True"):
            self.assertFalse(g.execute(plan, prog.write, apply=flag, rollback_path=rb, **self.ledger())["applied"])
        self.assertEqual(prog.calls, [])
        self.assertFalse(os.path.exists(rb))

    def test_apply_needs_a_rollback_path_and_a_ledger(self):
        self.refused("rollback file path", g.execute, self.plan([(67, 14)]), FakeProgrammer().write,
                     apply=True, **self.ledger())
        self.refused("ledger", g.execute, self.plan([(67, 14)]), FakeProgrammer().write,
                     apply=True, rollback_path=os.path.join(self.dir, "rb.json"))

    def test_apply_writes_in_order_and_saves_rollback_first(self):
        plan = self.plan([(25, 16), (67, 14), (68, 27), (29, 34)], reads={67: 9, 25: 16})
        rb = os.path.join(self.dir, "rb.json")
        seen = []
        prog = FakeProgrammer()

        def write(cv, value):
            seen.append(os.path.exists(rb))
            return prog.write(cv, value)
        res = g.execute(plan, write, apply=True, rollback_path=rb, **self.ledger())
        self.assertTrue(all(seen))
        self.assertEqual(prog.calls, [(67, 14), (68, 27), (29, 34)])  # only 25 was read equal
        self.assertEqual(res["written"], [67, 68, 29])
        doc = json.loads(Path(rb).read_text())
        self.assertEqual(doc["roster_id"], "CSX 2738")
        self.assertEqual(doc["old_values_from"], "mixed")
        self.assertEqual([(w["cv"], w["value"], w["old_source"]) for w in doc["writes"]],
                         [(25, 16, "read"), (67, 9, "read"), (68, 27, "roster"), (29, 50, "roster")])
        back = g.build_plan(doc, self.roster(), g.parse_consist_log(CLEAR))
        self.assertEqual([r["new"] for r in back["rows"]], [16, 9, 27, 50])

    def test_apply_will_not_overwrite_a_rollback(self):
        rb = os.path.join(self.dir, "rb.json")
        Path(rb).write_text("{}")
        prog = FakeProgrammer()
        self.refused("already exists", g.execute, self.plan([(67, 14)]), prog.write,
                     apply=True, rollback_path=rb, **self.ledger())
        self.assertEqual(prog.calls, [])

    def test_tampered_plan_is_caught_before_the_write(self):
        plan = self.plan([(67, 14), (68, 30)])
        plan["rows"][1]["cv"] = 17
        prog = FakeProgrammer()
        self.refused("CV17", g.execute, plan, prog.write, apply=True,
                     rollback_path=os.path.join(self.dir, "r.json"), **self.ledger())
        self.assertEqual(prog.calls, [(67, 14)])

    def test_tampered_skip_without_read_is_caught(self):
        plan = self.plan([(67, 12)])
        plan["rows"][0]["skip"] = True
        self.refused("skip without a read", g.execute, plan, FakeProgrammer().write, apply=True,
                     rollback_path=os.path.join(self.dir, "r.json"), **self.ledger())


# ---------------------------------------------------------------- pom_write.py with a fake jmri

class _Listener:
    OK, NoAck = 0, 0x20

    def programmingOpReply(self, value, status):  # overridden by the script's subclass
        pass


class _Prog:
    def __init__(self, number, is_long, log, mode):
        self.number, self.is_long, self.log, self.mode = number, is_long, log, mode

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
        if self.mode.get("read") == "timeout":
            return  # never answers
        if self.mode.get("read") == "ok":
            listener.programmingOpReply(self.mode["values"][int(cv)], _Listener.OK)
        else:
            listener.programmingOpReply(0, _Listener.NoAck)  # no RailCom: reads fail

    def writeCV(self, cv, value, listener):
        self.log.append(("write", cv, value))
        if self.mode.get("write_timeout") == int(cv):
            return
        listener.programmingOpReply(value, _Listener.OK)


def fake_jmri(roster_dir, calls, roster_number=2738, mode=None):
    jmri = types.ModuleType("jmri")
    jmri.ProgListener = _Listener
    mode = mode or {}

    class AddressedProgrammerManager:
        pass

    class OlcbProgrammerManager(AddressedProgrammerManager):
        def getAddressedProgrammer(self, is_long, number):
            calls.append(("programmer", is_long, number))
            return _Prog(number, is_long, calls, mode)

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
    def run_writer(self, apply, consist_log=CLEAR, guard_path=None, roster_number=2738,
                   absent_ok=None, mode=None, writes=((67, 14), (29, 34)), rollback="rollback.json"):
        roster_dir = make_roster(os.path.join(self.dir, "u"))
        prop = os.path.join(self.dir, "proposal.json")
        Path(prop).write_text(json.dumps(proposal(list(writes))))
        fake_query = os.path.join(self.dir, "fake_consist.py")
        with open(fake_query, "w") as f:
            f.write("import json\nwith open(LOGF + '.nodes', 'w') as q:\n    json.dump(NODES, q)\n"
                    "with open(LOGF, 'w') as q:\n    q.write(%r)\nRESULT = 'started'\n" % consist_log)
        logf = os.path.join(self.dir, "pom.log")
        rb = os.path.join(self.dir, rollback)
        calls = []
        env = {"__name__": "pom_write_test", "PROPOSAL": prop, "GUARD_PATH": guard_path or str(GUARD_PATH),
               "CONSIST_SCRIPT": fake_query, "LOGF": logf, "ROLLBACK": rb, "APPLY": apply,
               "LEDGER_DIR": os.path.join(self.dir, "ledger"), "RUN_INLINE": True,
               "OP_TIMEOUT": 0.05, "CONSIST_TIMEOUT": 2.0,
               "execfile": lambda path, e: exec(Path(path).read_text(), e)}
        if absent_ok is not None:
            env["ABSENT_OK"] = absent_ok
        with mock.patch.dict(sys.modules, {"jmri": fake_jmri(roster_dir, calls, roster_number, mode)}):
            exec(compile(WRITER_PATH.read_text(), str(WRITER_PATH), "exec"), env)
        self.queried = json.loads(Path(logf + ".consist.nodes").read_text()) \
            if os.path.exists(logf + ".consist.nodes") else None
        return Path(logf).read_text().splitlines(), calls, rb

    def test_dry_run_reads_but_does_not_write(self):
        lines, calls, rb = self.run_writer(apply=False)
        self.assertIn(("programmer", True, 2738), calls)
        self.assertFalse([c for c in calls if c[0] == "write"])
        self.assertIn("PLAN 2738L CV67 old=12 (roster) new=14", lines)
        self.assertTrue(any(line.startswith("DRY RUN") for line in lines))
        self.assertFalse(os.path.exists(rb))
        self.assertTrue(os.path.exists(rb + ".dryrun"))
        self.assertEqual(lines[-1], "END")

    def test_queries_every_roster_node(self):
        self.run_writer(apply=False)
        self.assertEqual(self.queried, [N2738, N2121, N06])

    def test_apply_writes_through_the_addressed_programmer_and_records_the_ledger(self):
        lines, calls, rb = self.run_writer(apply=True)
        self.assertEqual([c for c in calls if c[0] == "write"], [("write", "67", 14), ("write", "29", 34)])
        self.assertTrue(os.path.exists(rb))
        self.assertIn("DONE 2 write(s)", lines)
        led = g.load_ledger(os.path.join(self.dir, "ledger", "CSX_2738.json"), "CSX 2738")
        self.assertEqual((led["cvs"]["67"]["value"], led["cvs"]["29"]["value"]), (14, 34))

    def test_dry_run_reads_are_saved_and_used_by_the_apply(self):
        mode = {"read": "ok", "values": {67: 9, 29: 50}}
        lines, _, _ = self.run_writer(apply=False, mode=mode)
        self.assertIn("PLAN 2738L CV67 old=9 (read) new=14", lines)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "ledger", "CSX_2738.reads.json")))
        lines, calls, rb = self.run_writer(apply=True, rollback="rb2.json")  # reads fail this time
        self.assertIn("PLAN 2738L CV67 old=9 (reads_file) new=14", lines)
        doc = json.loads(Path(rb).read_text())
        self.assertEqual(doc["writes"][0]["value"], 9)

    def test_read_timeout_aborts_before_any_write(self):
        lines, calls, rb = self.run_writer(apply=True, mode={"read": "timeout"})
        self.assertFalse([c for c in calls if c[0] == "write"])
        self.assertTrue(any(line.startswith("ABORTED: read of CV67 timed out") for line in lines))
        self.assertFalse(os.path.exists(rb))

    def test_write_timeout_marks_unknown_and_says_so(self):
        lines, calls, rb = self.run_writer(apply=True, mode={"write_timeout": 67})
        self.assertEqual([c for c in calls if c[0] == "write"], [("write", "67", 14)])
        self.assertTrue(lines[-2].startswith("STOPPED: CV67 timed out"))
        led = g.load_ledger(os.path.join(self.dir, "ledger", "CSX_2738.json"), "CSX 2738")
        self.assertEqual(led["cvs"]["67"]["state"], "unknown")
        lines, calls, _ = self.run_writer(apply=True, rollback="rb2.json")
        self.assertTrue(any("CV67 is unknown in the ledger" in line for line in lines))
        self.assertFalse([c for c in calls if c[0] == "write"])

    def test_consist_present_refuses_before_any_programmer(self):
        lines, calls, _ = self.run_writer(apply=True, consist_log=CONSISTED)
        self.assertEqual(calls, [])
        self.assertTrue(any(line.startswith("REFUSED") and "consist" in line for line in lines))

    def test_absent_node_needs_absent_ok(self):
        log = qlog({N2738: [], N2121: [], N06: None})
        lines, calls, _ = self.run_writer(apply=False, consist_log=log)
        self.assertEqual(calls, [])
        self.assertTrue(any("'NWR 06'" in line and line.startswith("REFUSED") for line in lines))
        lines, calls, _ = self.run_writer(apply=False, consist_log=log, absent_ok=["NWR 06"])
        self.assertIn("ABSENT_OK 'NWR 06' train node %s did not answer" % N06, lines)

    def test_missing_guard_refuses(self):
        lines, calls, _ = self.run_writer(apply=True, guard_path=os.path.join(self.dir, "nope.py"))
        self.assertEqual(calls, [])
        self.assertTrue(lines[0].startswith("REFUSED guard module could not be loaded"))

    def test_jmri_roster_disagreeing_with_file_refuses(self):
        lines, calls, _ = self.run_writer(apply=True, roster_number=2739)
        self.assertEqual(calls, [])
        self.assertTrue(any("disagrees with roster file" in line for line in lines))


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
