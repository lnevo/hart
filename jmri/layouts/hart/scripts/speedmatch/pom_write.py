# pom_write.py - programming on the main (POM) for the speed-matching tools, behind pom_guard.
#
# Runs inside the Pi's JMRI (Jython 2.7), the host that owns the LCC link to the CS-105,
# dropped through jmri_cmd_watcher.py with its settings prepended as globals:
#
#   PROPOSAL = "/tmp/speedmatch/proposal.json"     the proposal (schema in pom_guard.py)
#   GUARD_PATH = "/tmp/speedmatch/pom_guard.py"    the guard; no guard, no write
#   CONSIST_SCRIPT = "/tmp/speedmatch/cs105_consist.py"   run with ACTION = "query" first
#   ABSENT_OK = []                                 roster ids whose train node may not answer
#   LOGF = "/tmp/pom_write.log"                    result lines, ends with END
#   ROLLBACK = "/home/pi/speedmatch/rollback_<id>_<time>.json"   must not exist yet
#   LEDGER_DIR = "/home/pi/speedmatch/ledger"      per-loco ledger and saved reads (default ~/speedmatch/ledger)
#   APPLY = False                                  True (exactly) to write; anything else is a dry run
#   READ_FIRST = True                              try a POM read of each CV for the old values
#   OP_TIMEOUT = 10.0                              seconds to wait for each ProgListener reply
#
# Steps: load the guard (refuse if it will not load); check the proposal, the roster files
# and JMRI's own roster entry; query the consist state of EVERY roster loco's train node and
# check it; get the addressed programmer for the roster address from the CS-105 connection's
# AddressedProgrammerManager (an OlcbProgrammer: an addressed memory-config write to the
# loco's train node, space 0xF8); read the old values where the decoder answers (a read that
# times out aborts the run, since it may still be in flight); build the plan through the
# guard (old values: read > saved reads file > ledger > roster); then write one CV at a time,
# waiting for each reply. The guard re-checks every row before its write, records each OK
# write in the ledger, and on a failed or timed-out write marks that CV unknown and stops.
#
# Without RailCom a POM write cannot be confirmed: JMRI 5.16 OlcbProgrammer reports OK when
# the CS-105 answers "no RailCom", so OK means "sent", and the check is the re-measure.
#
# Never touches track power, emergency stop, throttles, turnouts or MQTT.
import os, threading, time
import jmri


def _load_guard(path):
    try:
        import imp  # Jython 2.7
        return imp.load_source("pom_guard", path)
    except ImportError:  # CPython 3.12+ (tests)
        import importlib.util
        spec = importlib.util.spec_from_file_location("pom_guard", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

_G = globals()
_LOGF = _G.get("LOGF", "/tmp/pom_write.log")
_APPLY = _G.get("APPLY", False) is True
_READ_FIRST = _G.get("READ_FIRST", True) is True
_TIMEOUT = float(_G.get("OP_TIMEOUT", 10.0))
_CONSIST_TIMEOUT = float(_G.get("CONSIST_TIMEOUT", 120.0))  # every roster node, about 1.5 s each
_INLINE = _G.get("RUN_INLINE", False) is True   # tests only: run in the caller's thread

_log = open(_LOGF, "w")


def L(m):
    _log.write("%s\n" % m)
    _log.flush()


class _Reply(jmri.ProgListener):
    def __init__(self):
        self.ev = threading.Event()
        self.value = None
        self.status = None

    def programmingOpReply(self, value, status):
        self.value = value
        self.status = status
        self.ev.set()


def _op(prog, start):
    r = _Reply()
    start(r)
    r.ev.wait(_TIMEOUT)
    if not r.ev.is_set():
        return None, None, "timeout after %.0fs" % _TIMEOUT
    text = "status %d" % r.status
    try:
        text = "%s (%s)" % (text, prog.decodeErrorCode(r.status))
    except Exception:
        pass
    return r.value, r.status, text


def _consist_query(nodes):
    path = _G["CONSIST_SCRIPT"]
    qlog = _LOGF + ".consist"
    if os.path.exists(qlog):
        os.remove(qlog)
    env = {"ACTION": "query", "NODES": list(nodes), "LOGF": qlog}
    execfile(path, env)
    end = time.time() + _CONSIST_TIMEOUT
    text = ""
    while time.time() < end:
        if os.path.exists(qlog):
            qf = open(qlog)
            try:
                text = qf.read()
            finally:
                qf.close()
            if "\nEND" in "\n" + text:
                break
        time.sleep(0.5)
    for line in text.splitlines():
        L("CONSIST %s" % line)
    return text


def _run():
    try:
        try:
            guard = _load_guard(_G["GUARD_PATH"])
        except Exception as e:
            L("REFUSED guard module could not be loaded: %s" % e)
            return
        R = guard.GuardRefusal
        try:
            proposal = guard.load_proposal(_G["PROPOSAL"])
            rid, writes = guard.validate_proposal(proposal)

            # Roster: JMRI's own entry and the files on disk must agree.
            jroster = jmri.jmrit.roster.Roster.getDefault()
            je = jroster.getEntryForId(rid)
            if je is None:
                raise R("JMRI has no roster entry %r" % rid)
            roster = guard.load_roster(jroster.getRosterLocation())
            entry = guard.check_roster_target(roster, rid)
            if int(je.getDccAddress()) != entry["number"] or bool(je.isLongAddress()) != entry["long"]:
                raise R("JMRI roster entry %r (%s%s) disagrees with roster file (%d%s)" % (
                    rid, je.getDccAddress(), "L" if je.isLongAddress() else "S",
                    entry["number"], "L" if entry["long"] else "S"))
            absent_ok = _G.get("ABSENT_OK", [])
            if not isinstance(absent_ok, list):
                raise R("ABSENT_OK must be a list of roster ids")
            ledger_dir = _G.get("LEDGER_DIR") or os.path.expanduser("~/speedmatch/ledger")
            ledger_file = guard.ledger_path(ledger_dir, rid)
            reads_file = guard.reads_path(ledger_dir, rid)
            ledger = guard.load_ledger(ledger_file, rid)
            saved = guard.load_reads_file(reads_file, rid, entry["number"], entry["long"])

            # Consist: query every roster loco's train node now; the guard fails closed.
            nodes = guard.query_nodes(roster, rid)
            state = guard.parse_consist_log(_consist_query([n for _, n in nodes]))
            guard.check_no_consist(state, nodes, absent_ok)

            # Programmer: the CS-105 connection's addressed programmer for the roster address.
            memo = jmri.InstanceManager.getNullableDefault(jmri.jmrix.can.CanSystemConnectionMemo)
            if memo is None:
                raise R("no LCC (CAN) connection")
            apm = memo.get(jmri.AddressedProgrammerManager)
            if apm is None or not isinstance(apm, jmri.jmrix.openlcb.OlcbProgrammerManager):
                raise R("the LCC connection has no OpenLCB addressed programmer manager")
            prog = apm.getAddressedProgrammer(entry["long"], entry["number"])
            if prog is None:
                raise R("no addressed programmer for %d" % entry["number"])
            if prog.getAddressNumber() != entry["number"] or bool(prog.getLongAddress()) != entry["long"]:
                raise R("programmer address %s does not match the roster" % prog.getAddress())
            L("PROGRAMMER %s for %r" % (prog.getAddress(), rid))

            # Old values: a POM read where the decoder answers. A failed read stops reading;
            # a read that times out aborts, since it may still be in flight.
            reads = {}
            if _READ_FIRST:
                for cv, _ in writes:
                    value, status, text = _op(prog, lambda r, c=cv: prog.readCV(str(c), r))
                    if status is None:
                        L("ABORTED: read of CV%d timed out (%s) and may still be in flight; nothing "
                          "written" % (cv, text))
                        return
                    if status == jmri.ProgListener.OK:
                        reads[cv] = value
                        L("READ CV%d=%d" % (cv, value))
                    else:
                        L("READ CV%d failed: %s; no more reads, using reads file, ledger or roster"
                          % (cv, text))
                        break
            reads = guard.validate_reads(reads)
            if reads:
                guard.ledger_note_reads(ledger, reads)
                guard._write_json(ledger_file, ledger)
                if len(reads) == len(writes):
                    guard.save_reads(reads_file, entry, rid, reads)
                    L("READS saved %s" % reads_file)

            plan = guard.build_plan(proposal, roster, state, absent_ok=absent_ok, reads=reads,
                                    reads_file=saved, ledger=ledger)

            def write_cv(cv, value):
                _, status, text = _op(prog, lambda r: prog.writeCV(str(cv), value, r))
                if status is None:
                    return "timeout", text
                time.sleep(0.2)
                return ("ok" if status == jmri.ProgListener.OK else "failed"), text

            guard.execute(plan, write_cv, apply=_APPLY, rollback_path=_G.get("ROLLBACK"),
                          ledger=ledger, ledger_file=ledger_file, log=L)
        except R as e:
            L("REFUSED %s" % e)
    except Exception as e:
        L("ERROR %s" % e)
    finally:
        L("END")
        _log.close()


if _INLINE:
    _run()
else:
    _t = threading.Thread(target=_run, name="pom_write")
    _t.setDaemon(True)
    _t.start()
RESULT = "started"
