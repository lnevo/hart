# cs105_consist.py - query, attach or detach an LCC consist on the TCS CS-105.
#
# Runs inside the Pi's JMRI (Jython 2.7), the host that owns the LCC link, normally
# dropped through jmri_cmd_watcher.py by tools/ops/cs105.sh consist, with its settings prepended:
#
#   ACTION = "query"    NODES = ["06.01.00.00.C8.49", ...]   train nodes to ask
#   ACTION = "attach"   LEAD = "<lead train node>"  FOLLOW = "<follower train node>"  FLAGS = 6
#   ACTION = "detach"   LEAD = ...                  FOLLOW = ...
#   LOGF = "/tmp/consist.log"                        result lines go here, ends with END
#
# It sends the Train Control "listener" messages (0x30 attach 0x01 / detach 0x02 / query
# 0x03) straight to the lead train node. It does NOT assign a controller, so it does not
# take a loco away from a throttle. FLAGS: 0x02 reverse, 0x04 link F0, 0x08 link other
# functions. 6 = follower runs in reverse and its headlight follows the lead's F0.
# A consist is made with one attach per side (LEAD lists FOLLOW, then FOLLOW lists LEAD);
# detach removes the listener on both nodes and queries both. A detach of a listener
# a node does not hold is harmless; the query afterwards shows the real state.
# Train node of a long DCC address: 06.01.00.00.(C0|hi).lo (CSX 2121 = C8.49,
# CSX 2738 = CA.B2). Bytes above 127 must be sent as signed values (Jython).
# Never touches track power, turnouts or throttles.
#
# The log is read by cs105.sh (a line starting ERROR fails the run) and by the POM guard
# (speedmatch/pom_guard_roster.parse_consist_log: an ERROR or "decode error" line refuses the
# write). A reply JMRI cannot read is logged as a decode error, never dropped.
import time, threading, jarray, jmri, java
from org.openlcb import NodeID, MessageDecoder, OlcbInterface
from org.openlcb.messages import TractionControlRequestMessage as Req

QUERY_WAIT = 1.5     # seconds for a node to answer the count query
ENTRY_WAIT = 1.2     # seconds for a node to answer one listener entry
CHANGE_WAIT = 2      # seconds after an attach or detach before the next message


class ConsistLog(object):
    """The result file; close() writes END, the line its readers wait for, and closes it."""

    def __init__(self, path):
        self._lock = threading.Lock()
        self._f = open(path, "w")

    def line(self, m):
        self._lock.acquire()
        try:
            if self._f is not None:
                self._f.write("%s\n" % (m,))
                self._f.flush()
        finally:
            self._lock.release()

    def close(self):
        self._lock.acquire()
        try:
            if self._f is not None:
                self._f.write("END\n")
                self._f.close()
                self._f = None
        finally:
            self._lock.release()


log = ConsistLog(LOGF)  # LOGF, ACTION, NODES, LEAD, FOLLOW, FLAGS: settings prepended by the dropper


def L(m):
    log.line(m)


replies = []


class Replies(MessageDecoder):
    """Collects every Train Control listener reply (0x30) with the node that sent it."""

    def handleTractionControlReply(self, msg, sender):
        try:
            if msg.getCmd() == 0x30:
                replies.append((str(msg.getSourceNodeID()), msg))
        except Exception as e:
            L("reply decode error %s" % (e,))


def lcc_interface():
    """The OpenLCB interface of this JMRI's CAN connection; RuntimeError when there is none."""
    memo = jmri.InstanceManager.getNullableDefault(jmri.jmrix.can.CanSystemConnectionMemo)
    if memo is None:
        raise RuntimeError("no LCC (CAN) connection in this JMRI")
    iface = memo.get(OlcbInterface)
    if iface is None:
        raise RuntimeError("the CAN connection has no OpenLCB interface")
    return iface


def send(dst, data):
    signed = jarray.array([(x if x < 128 else x - 256) for x in data], 'b')
    iface.getOutputConnection().put(Req(iface.getNodeId(), NodeID(dst), signed), None)


def listener_payload(sub, flags, node):
    # Listener attach (0x01) and detach (0x02) are 9 bytes: 0x30, sub, flags, then the
    # 6-byte node id (OpenLCB TractionControlRequestMessage.createConsistAttach/Detach).
    # Without the flags byte the CS-105 reads the wrong node and changes nothing.
    b = [int(x, 16) for x in node.split(".")]
    if len(b) != 6 or [x for x in b if x < 0 or x > 255]:
        raise ValueError("node id %r is not 6 bytes" % (node,))
    return [0x30, sub, flags] + b


def replies_from(node):
    return [m for src, m in list(replies) if src.upper() == node.upper()]


def listener_count(node):
    """The number of listeners `node` reports, or None when it does not answer."""
    del replies[:]
    send(node, [0x30, 0x03])
    time.sleep(QUERY_WAIT)
    n = None
    errors = []
    for m in replies_from(node):
        try:
            n = m.getConsistLength()
        except Exception as e:
            errors.append(e)
    # A stray reply of another kind from the same node (a late attach or detach answer) does not
    # read as a count; it is an error, and the POM guard refuses on it, only when no reply gave one.
    if n is None and errors:
        L("%s count decode error %s" % (node, errors[-1]))
    return n


def log_entry(node, i):
    """Ask `node` for listener entry `i` and log each answer."""
    del replies[:]
    send(node, [0x30, 0x03, i])
    time.sleep(ENTRY_WAIT)
    for m in replies_from(node):
        try:
            p = [(x + 256) % 256 for x in m.getPayload()]
            L("  raw payload: %s" % " ".join("%02X" % x for x in p))
            # reply layout: 30 03 count index flags node(6)
            L("  [%d] flags 0x%02X node %s" % (p[3], p[4], ".".join("%02X" % x for x in p[5:11])))
        except Exception as e:
            L("  [%d] decode error %s" % (i, e))


def query(node):
    n = listener_count(node)
    L("%s listeners: %s" % (node, n))
    if not n:
        return
    for i in range(n):
        log_entry(node, i)


def change(action, lead, follow, flags):
    """Attach `follow` on `lead`, or detach the pair on both sides, then query both."""
    if action == "attach":
        send(lead, listener_payload(0x01, flags, follow))
        L("attach %s on %s flags 0x%02X" % (follow, lead, flags))
        time.sleep(CHANGE_WAIT)
    else:
        # each side lists the other, so drop the listener on both
        for a, b in ((lead, follow), (follow, lead)):
            send(a, listener_payload(0x02, 0, b))
            L("detach %s on %s" % (b, a))
            time.sleep(CHANGE_WAIT)
    for n in (lead, follow):
        query(n)


def run():
    try:
        try:
            if ACTION == "query":
                for n in NODES:
                    query(n)
            elif ACTION in ("attach", "detach"):
                change(ACTION, LEAD, FOLLOW, FLAGS)
            else:
                L("ERROR unknown ACTION %r" % (ACTION,))
        except (Exception, java.lang.Throwable) as e:
            L("ERROR %s" % (e,))
    finally:
        iface.unRegisterMessageListener(h)
        log.close()


try:
    iface = lcc_interface()
    h = Replies()
    iface.registerMessageListener(h)
except (Exception, java.lang.Throwable) as e:
    L("ERROR %s" % (e,))
    log.close()
    raise
t = threading.Thread(target=run)
t.setDaemon(True)
t.start()
RESULT = "started"
