# pom_write.py - programming on the main (POM) for the speed-matching tools, behind pom_guard.
#
# Runs inside the Pi's JMRI (Jython 2.7), the host that owns the LCC link to the CS-105,
# dropped through jmri_cmd_watcher.py with its settings prepended as globals:
#
#   PROPOSAL = "/tmp/speedmatch/proposal.json"     the proposal (schema in pom_guard.py)
#   GUARD_PATH = "/tmp/speedmatch/pom_guard.py"    the guard; no guard, no write
#   CONSIST_SCRIPT = "/tmp/speedmatch/cs105_consist.py"   run with ACTION = "query" first
#   ABSENT_OK = []                                 roster ids whose train node may not answer
#   CONSISTS_BROKEN = False                        True (exactly), required for apply: the operator
#                                                  confirms every consist with this loco is broken,
#                                                  including leads that are not in the roster
#   ROSTER_OLD_OK = False                          True (exactly) lets an apply use roster values as old
#                                                  values (they may be defaults); seed-ledger is better
#   LOGF = "/tmp/pom_write.log"                    result lines, ends with END
#   ROLLBACK = "/home/pi/speedmatch/rollback_<id>_<time>.json"   must not exist yet
#   LEDGER_DIR = "/home/pi/speedmatch/ledger"      per-loco ledger (default ~/speedmatch/ledger)
#   APPLY = False                                  True (exactly) to write; anything else is a dry run
#   READ_FIRST = True                              try a POM read of each CV for the old values
#   OP_TIMEOUT = 10.0                              seconds to wait for each ProgListener reply
#
# Steps: load the guard (refuse if it will not load); query the consist state of every roster
# loco's train node; run the guard's checks once (proposal, roster target, consist); check
# JMRI's own roster entry against it; get the addressed programmer for the roster address from
# the CS-105 connection's AddressedProgrammerManager (an OlcbProgrammer: an addressed
# memory-config write to the loco's train node, space 0xF8); read the old values where the
# decoder answers and record them in the ledger (a read that times out aborts the run, since
# it may still be in flight); plan through the guard (old values: read > ledger > roster);
# then write one CV at a time, waiting for each reply. The guard re-checks every row before
# its write, records each OK write in the ledger, and on a failed or timed-out write marks
# that CV unknown, stops, and logs the recovery steps.
#
# Without RailCom a POM write cannot be confirmed: JMRI 5.16 OlcbProgrammer reports OK when
# the CS-105 answers "no RailCom", so OK means "sent", and the check is the re-measure.
#
# Never touches track power, emergency stop, throttles, turnouts or MQTT.
import os, threading, time
import jmri

try:
    from java.lang import Throwable as _Throwable  # Jython: Java exceptions are not Exceptions
except ImportError:  # CPython tests
    _Throwable = Exception
_ANY = (Exception, _Throwable)
_EXC = "EXC"  # _op status for an exception raised while starting the operation


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
    try:
        start(r)
    except _ANY as e:
        return None, _EXC, "exception %s" % (e,)
    r.ev.wait(_TIMEOUT)
    if not r.ev.is_set():
        return None, None, "timeout after %.0fs" % _TIMEOUT
    text = "status %d" % r.status
    try:
        text = "%s (%s)" % (text, prog.decodeErrorCode(r.status))
    except Exception:
        pass
    return r.value, r.status, text


def _consist_query(nodes, refuse):
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
            if any(line.strip() == "END" for line in text.splitlines()):
                break
        time.sleep(0.5)
    for line in text.splitlines():
        L("CONSIST %s" % line)
    if not any(line.strip() == "END" for line in text.splitlines()):
        raise refuse("consist query did not finish in %.0fs; its thread may still be running in "
                     "JMRI. Wait until %s ends with a line END, then run again" % (_CONSIST_TIMEOUT, qlog))
    return text


def _run():
    held = []  # the lock file, once this run holds it
    guard = None
    try:
        try:
            guard = _load_guard(_G["GUARD_PATH"])
        except _ANY as e:
            L("REFUSED guard module could not be loaded: %s" % e)
            return
        R = guard.GuardRefusal
        try:
            proposal = guard.load_proposal(_G["PROPOSAL"])
            absent_ok = _G.get("ABSENT_OK", [])
            if not isinstance(absent_ok, list):
                raise R("ABSENT_OK must be a list of roster ids")
            jroster = jmri.jmrit.roster.Roster.getDefault()
            roster = guard.load_roster(jroster.getRosterLocation())

            # Consist: query every roster loco's train node now, then run every guard check once.
            nodes = guard.query_nodes(roster, proposal.get("roster_id") if isinstance(proposal, dict) else None)
            state = guard.parse_consist_log(_consist_query([n for _, n in nodes], R))
            ctx = guard.prepare(proposal, roster, state, absent_ok)
            rid, address, is_long = ctx["roster_id"], ctx["address"], ctx["long"]

            # JMRI's own roster entry must agree with the files the guard read.
            je = jroster.getEntryForId(rid)
            if je is None:
                raise R("JMRI has no roster entry %r" % rid)
            if int(je.getDccAddress()) != address or bool(je.isLongAddress()) != is_long:
                raise R("JMRI roster entry %r (%s%s) disagrees with roster file (%d%s)" % (
                    rid, je.getDccAddress(), "L" if je.isLongAddress() else "S",
                    address, "L" if is_long else "S"))
            ledger_dir = _G.get("LEDGER_DIR") or guard.DEFAULT_LEDGER_DIR
            ledger_file = guard.ledger_path(ledger_dir, rid)
            held.append(guard.acquire_lock(guard.lock_path(ledger_dir, rid), "pom_write.py %s" % _LOGF))
            ledger = guard.load_ledger(ledger_file, rid)

            # Programmer: the CS-105 connection's addressed programmer for the roster address.
            memo = jmri.InstanceManager.getNullableDefault(jmri.jmrix.can.CanSystemConnectionMemo)
            if memo is None:
                raise R("no LCC (CAN) connection")
            apm = memo.get(jmri.AddressedProgrammerManager)
            if apm is None or not isinstance(apm, jmri.jmrix.openlcb.OlcbProgrammerManager):
                raise R("the LCC connection has no OpenLCB addressed programmer manager")
            prog = apm.getAddressedProgrammer(is_long, address)
            if prog is None:
                raise R("no addressed programmer for %d" % address)
            if prog.getAddressNumber() != address or bool(prog.getLongAddress()) != is_long:
                raise R("programmer address %s does not match the roster" % prog.getAddress())
            L("PROGRAMMER %s for %r" % (prog.getAddress(), rid))

            # Old values: a POM read where the decoder answers, recorded in the ledger. A failed
            # read stops reading; a read that times out aborts, since it may still be in flight.
            reads = {}
            if _READ_FIRST:
                for cv, _ in ctx["writes"]:
                    value, status, text = _op(prog, lambda r, c=cv: prog.readCV(str(c), r))
                    if status is None or status == _EXC:
                        L("ABORTED: read of CV%d %s (%s)%s. Nothing was written and the ledger is "
                          "unchanged; wait, then run again" % (
                              cv, "timed out" if status is None else "raised an exception", text,
                              " and may still be in flight" if status is None else ""))
                        return
                    if status == jmri.ProgListener.OK:
                        reads[cv] = value
                        L("READ CV%d=%d" % (cv, value))
                    else:
                        L("READ CV%d failed: %s; no more reads, using ledger or roster" % (cv, text))
                        break
            reads = guard.validate_reads(reads)
            if reads:
                guard.ledger_note_reads(ledger, reads)
                guard._write_json(ledger_file, ledger)
                L("LEDGER reads recorded in %s" % ledger_file)

            plan = guard.plan_rows(ctx, reads=reads, ledger=ledger)

            def write_cv(cv, value):
                _, status, text = _op(prog, lambda r: prog.writeCV(str(cv), value, r))
                if status is None:
                    return "timeout", text
                if status == _EXC:
                    return "exception", text
                time.sleep(0.2)
                return ("ok" if status == jmri.ProgListener.OK else "failed"), text

            guard.execute(plan, write_cv, apply=_APPLY,
                          consists_broken=_G.get("CONSISTS_BROKEN", False) is True,
                          roster_old_ok=_G.get("ROSTER_OLD_OK", False) is True,
                          rollback_path=_G.get("ROLLBACK"), ledger=ledger, ledger_file=ledger_file, log=L)
        except R as e:
            L("REFUSED %s" % e)
    except _ANY as e:
        L("ERROR %s" % (e,))
    finally:
        if held:
            try:
                guard.release_lock(held[0])
            except _ANY as e:
                L("ERROR lock %s not removed: %s" % (held[0], e))
        L("END")
        _log.close()


if _INLINE:
    _run()
else:
    _t = threading.Thread(target=_run, name="pom_write")
    _t.setDaemon(True)
    _t.start()
RESULT = "started"
