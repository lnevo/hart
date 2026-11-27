"""cs105_consist.py, run whole under CPython against a fake JMRI and a fake CS-105: the messages it sends, the
log it writes for cs105.sh and the POM guard, and the errors it logs instead of dropping."""
import runpy
import sys
import tempfile
import types
import unittest
import warnings
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "cs105_consist.py"
sys.path.insert(0, str(HERE.parent / "speedmatch"))
import pom_guard_roster  # noqa: E402  the log's reader in the POM guard

A = "06.01.00.00.C8.49"
B = "06.01.00.00.CA.B2"


class Throwable(BaseException):
    """java.lang.Throwable: not a Python Exception, as in Jython."""


class Reply:
    def __init__(self, src, payload, length=None, cmd=0x30, bad=None):
        self.src, self.payload, self.length, self.cmd, self.bad = src, payload, length, cmd, bad

    def getCmd(self):
        if self.bad == "cmd":
            raise ValueError("unreadable reply")
        return self.cmd

    def getSourceNodeID(self):
        return self.src

    def getConsistLength(self):
        if self.bad == "length":
            raise ValueError("no length")
        return self.length

    def getPayload(self):
        if self.bad == "payload":
            raise ValueError("short payload")
        return [x if x < 128 else x - 256 for x in self.payload]


class FakeCs105:
    """Answers listener queries from `listeners` {node: [(flags, node)]}; records every message sent."""

    def __init__(self, listeners, bad=None):
        self.listeners, self.bad = listeners, bad
        self.sent, self.handlers, self.unregistered = [], [], []

    def registerMessageListener(self, h):
        self.handlers.append(h)

    def unRegisterMessageListener(self, h):
        self.unregistered.append(h)

    def getNodeId(self):
        return "02.01.57.00.00.01"

    def getOutputConnection(self):
        return self

    def put(self, msg, _):
        dst, data = msg
        data = [(x + 256) % 256 for x in data]
        self.sent.append((dst, data))
        if data[:2] != [0x30, 0x03] or dst not in self.listeners:
            return
        entries = self.listeners[dst]
        if len(data) == 2:
            reply = Reply(dst, [0x30, 0x03, len(entries)], length=len(entries), bad=self.bad)
        else:
            flags, node = entries[data[2]]
            reply = Reply(dst, [0x30, 0x03, len(entries), data[2], flags] + [int(x, 16) for x in node.split(".")],
                          bad=self.bad)
        for h in self.handlers:
            h.handleTractionControlReply(reply, None)


def fake_modules(iface):
    """sys.modules entries for jarray, jmri, java and org.openlcb, backed by `iface` (None: no CAN connection)."""
    memo_cls = type("CanSystemConnectionMemo", (), {})
    olcb_cls = type("OlcbInterface", (), {})
    memo = None if iface is None else types.SimpleNamespace(get=lambda cls: iface if cls is olcb_cls else None)
    jmri = types.SimpleNamespace(
        InstanceManager=types.SimpleNamespace(getNullableDefault=lambda cls: memo if cls is memo_cls else None),
        jmrix=types.SimpleNamespace(can=types.SimpleNamespace(CanSystemConnectionMemo=memo_cls)))
    org = types.ModuleType("org")
    openlcb = types.ModuleType("org.openlcb")
    openlcb.NodeID = str
    openlcb.MessageDecoder = object
    openlcb.OlcbInterface = olcb_cls
    messages = types.ModuleType("org.openlcb.messages")
    messages.TractionControlRequestMessage = lambda src, dst, data: (dst, list(data))
    return {"jarray": types.SimpleNamespace(array=lambda values, code: list(values)),
            "jmri": jmri, "java": types.SimpleNamespace(lang=types.SimpleNamespace(Throwable=Throwable)),
            "org": org, "org.openlcb": openlcb, "org.openlcb.messages": messages}


class Run(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.logf = Path(tmp.name) / "consist.log"
        sleep = mock.patch("time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def run_script(self, iface, **settings):
        """Run the script as the dropper does, wait for its thread, return (globals, log lines)."""
        settings.setdefault("NODES", [])
        settings.setdefault("LEAD", A)
        settings.setdefault("FOLLOW", B)
        settings.setdefault("FLAGS", 6)
        with mock.patch.dict(sys.modules, fake_modules(iface)), warnings.catch_warnings():
            warnings.filterwarnings("ignore", "setDaemon", DeprecationWarning)   # the call Jython 2.7 has
            env = runpy.run_path(str(SRC), init_globals=dict(settings, LOGF=str(self.logf)))
        env["t"].join(10)
        self.assertFalse(env["t"].is_alive())
        return env, self.logf.read_text().splitlines()

    def test_query_logs_each_listener_and_the_guard_reads_it(self):
        cs = FakeCs105({A: [(0x06, B)], B: []})
        env, lines = self.run_script(cs, ACTION="query", NODES=[A, B, "06.01.00.00.C0.03"])
        self.assertEqual(env["RESULT"], "started")
        self.assertEqual(lines, [
            A + " listeners: 1",
            "  raw payload: 30 03 01 00 06 06 01 00 00 CA B2",
            "  [0] flags 0x06 node 06.01.00.00.CA.B2",
            B + " listeners: 0",
            "06.01.00.00.C0.03 listeners: None",
            "END"])
        self.assertEqual(cs.sent, [(A, [0x30, 0x03]), (A, [0x30, 0x03, 0]), (B, [0x30, 0x03]),
                                   ("06.01.00.00.C0.03", [0x30, 0x03])])
        self.assertEqual(cs.unregistered, cs.handlers)
        state = pom_guard_roster.parse_consist_log("\n".join(lines))
        self.assertTrue(state["complete"])
        self.assertEqual(state["errors"], [])
        self.assertEqual(state["nodes"][A]["listeners"], [B])

    def test_attach_sends_the_9_byte_listener_message_then_queries_both(self):
        cs = FakeCs105({A: [], B: []})
        _, lines = self.run_script(cs, ACTION="attach", FLAGS=6)
        self.assertEqual(cs.sent[0], (A, [0x30, 0x01, 0x06, 0x06, 0x01, 0x00, 0x00, 0xCA, 0xB2]))
        self.assertEqual([d for d, _ in cs.sent[1:]], [A, B])
        self.assertEqual(lines[0], "attach %s on %s flags 0x06" % (B, A))
        self.assertEqual(lines[-1], "END")

    def test_detach_drops_the_listener_on_both_sides_and_queries_both(self):
        cs = FakeCs105({A: [], B: []})
        _, lines = self.run_script(cs, ACTION="detach")
        self.assertEqual(cs.sent[:2], [(A, [0x30, 0x02, 0x00, 0x06, 0x01, 0x00, 0x00, 0xCA, 0xB2]),
                                       (B, [0x30, 0x02, 0x00, 0x06, 0x01, 0x00, 0x00, 0xC8, 0x49])])
        self.assertEqual([d for d, _ in cs.sent[2:]], [A, B])
        self.assertEqual(lines[:2], ["detach %s on %s" % (B, A), "detach %s on %s" % (A, B)])

    def test_a_node_id_that_is_not_6_bytes_is_an_error_line(self):
        cs = FakeCs105({})
        _, lines = self.run_script(cs, ACTION="attach", FOLLOW="06.01.00.00.CA")
        self.assertEqual(cs.sent, [])
        self.assertEqual(lines, ["ERROR node id '06.01.00.00.CA' is not 6 bytes", "END"])

    def test_an_unknown_action_is_an_error_line(self):
        _, lines = self.run_script(FakeCs105({}), ACTION="split")
        self.assertEqual(lines, ["ERROR unknown ACTION 'split'", "END"])

    def test_a_java_throwable_is_an_error_line(self):
        cs = FakeCs105({A: []})
        cs.getOutputConnection = mock.Mock(side_effect=Throwable("link down"))
        _, lines = self.run_script(cs, ACTION="query", NODES=[A])
        self.assertEqual(lines, ["ERROR link down", "END"])
        self.assertEqual(cs.unregistered, cs.handlers)

    def test_unreadable_replies_are_decode_errors_the_guard_refuses(self):
        for bad, want in (("cmd", "reply decode error unreadable reply"),
                          ("length", A + " count decode error no length"),
                          ("payload", "  [0] decode error short payload")):
            with self.subTest(bad=bad):
                cs = FakeCs105({A: [(0x06, B)]}, bad=bad if bad != "payload" else None)
                if bad == "payload":
                    real = cs.put

                    def put(msg, _, real=real, cs=cs):
                        cs.bad = "payload" if len(msg[1]) == 3 else None
                        real(msg, _)
                    cs.put = put
                _, lines = self.run_script(cs, ACTION="query", NODES=[A])
                self.assertIn(want, lines)
                self.assertTrue(pom_guard_roster.parse_consist_log("\n".join(lines))["errors"], lines)

    def test_a_stray_reply_beside_a_good_count_is_no_error(self):
        cs = FakeCs105({A: []})
        real = cs.put

        def put(msg, _):
            if list(msg[1])[:2] == [0x30, 0x03] and len(msg[1]) == 2:   # a late answer of another kind first
                for h in cs.handlers:
                    h.handleTractionControlReply(Reply(A, [0x30, 0x01], bad="length"), None)
            real(msg, _)
        cs.put = put
        _, lines = self.run_script(cs, ACTION="query", NODES=[A])
        self.assertEqual(lines, [A + " listeners: 0", "END"])
        self.assertEqual(pom_guard_roster.parse_consist_log("\n".join(lines))["errors"], [])

    def test_no_can_connection_logs_the_error_ends_the_log_and_raises(self):
        with self.assertRaisesRegex(RuntimeError, "no LCC"), mock.patch.dict(sys.modules, fake_modules(None)):
            runpy.run_path(str(SRC), init_globals={"ACTION": "query", "NODES": [A], "LOGF": str(self.logf)})
        self.assertEqual(self.logf.read_text().splitlines(), ["ERROR no LCC (CAN) connection in this JMRI", "END"])


if __name__ == "__main__":
    unittest.main()
