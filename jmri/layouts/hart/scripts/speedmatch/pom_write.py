# pom_write.py - programming on the main (POM) for the speed-matching tools, behind pom_guard.
#
# Runs inside the Pi's JMRI (Jython 2.7), the host that owns the LCC link to the CS-105,
# dropped through jmri_cmd_watcher.py with its settings prepended as globals:
#
#   PROPOSAL = "/tmp/speedmatch/proposal.json"     the proposal (schema in pom_guard.py)
#   GUARD_PATH = "/tmp/speedmatch/pom_guard.py"    the guard; no guard, no write
#   CONSIST_SCRIPT = "/tmp/speedmatch/cs105_consist.py"   run with ACTION = "query" first
#   PARTNERS = ["CSX 2121"]                        roster ids whose consists must be empty too
#   LOGF = "/tmp/pom_write.log"                    result lines, ends with END
#   ROLLBACK = "/home/pi/speedmatch/rollback_<id>_<time>.json"   must not exist yet
#   APPLY = False                                  True (exactly) to write; anything else is a dry run
#   READ_FIRST = True                              try a POM read of each CV for the old values
#   OP_TIMEOUT = 10.0                              seconds to wait for each ProgListener reply
#
# Steps: load the guard (refuse if it will not load), check the proposal, the roster file
# and JMRI's own roster entry, run the consist query and check it, get the addressed
# programmer for the roster address from the CS-105 connection's AddressedProgrammerManager
# (an OlcbProgrammer: an addressed memory-config write to the loco's train node, space 0xF8),
# read the old values where the decoder answers, build the plan through the guard, then write
# one CV at a time, waiting for each reply, stopping at the first failure. The guard re-checks
# every row before its write, and the programmer's address is checked again each time.
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
_CONSIST_TIMEOUT = float(_G.get("CONSIST_TIMEOUT", 60.0))
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
            if not isinstance(_G.get("PARTNERS"), list):
                raise R("PARTNERS is not set: name the locos that consist with %r ([] for none)" % rid)
            partners = list(_G["PARTNERS"])
            nodes = [guard.train_node(entry["number"], entry["long"])]
            for p in partners:
                if p != rid:
                    if p not in roster:
                        raise R("consist partner %r is not in the roster" % (p,))
                    nodes.append(guard.train_node(roster[p]["number"], roster[p]["long"]))

            # Consist: query now, fail closed on anything but "no listeners".
            state = guard.parse_consist_log(_consist_query(nodes))
            guard.check_no_consist(state, nodes)

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

            def same_address():
                return (prog.getAddressNumber() == entry["number"]
                        and bool(prog.getLongAddress()) == entry["long"])
            if not same_address():
                raise R("programmer address %s does not match the roster" % prog.getAddress())
            L("PROGRAMMER %s for %r" % (prog.getAddress(), rid))

            # Old values: a POM read where the decoder answers, else the roster's values.
            reads = {}
            if _READ_FIRST:
                for cv, _ in writes:
                    value, status, text = _op(prog, lambda r, c=cv: prog.readCV(str(c), r))
                    if status == jmri.ProgListener.OK:
                        reads[cv] = value
                        L("READ CV%d=%d" % (cv, value))
                    else:
                        L("READ CV%d failed: %s; using roster values from here on" % (cv, text))
                        break

            plan = guard.build_plan(proposal, roster, state, partners=partners, reads=reads)

            def write_cv(cv, value):
                if not same_address():
                    return False, "programmer address changed to %s" % prog.getAddress()
                _, status, text = _op(prog, lambda r: prog.writeCV(str(cv), value, r))
                time.sleep(0.2)
                return status == jmri.ProgListener.OK, text

            guard.execute(plan, write_cv, apply=_APPLY, rollback_path=_G.get("ROLLBACK"), log=L)
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
