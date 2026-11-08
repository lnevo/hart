"""Restart the TCS CS-105 over LCC, then list the nodes that come back.

Runs inside the Pi's JMRI (drop it through jmri_cmd_watcher with
tools/ops/cs105_reboot.sh). It finds the CS-105 by its SNIP model name,
sends the OpenLCB Memory Configuration "Reset/Reboot" datagram (0x20 0xA9),
waits for the node to restart, refreshes JMRI's node store and reports every
node on the bus. The CS-105 does not acknowledge the datagram; it just reboots.

A restart drops live train nodes the CS-105 has not stored: a train is kept
across a restart only once it has a Train.Name (the roster sync sets one).
Track power goes off for a few seconds, so do not run this while trains move.
"""
import time

import jmri
from org.openlcb import NodeID, OlcbInterface
from org.openlcb.implementations import DatagramService

REBOOT_WAIT = 25.0   # seconds for the CS-105 to come back
REFRESH_WAIT = 12.0  # seconds for nodes to answer the refresh


def _nodes(store):
    ids = sorted(str(nm.getNodeID()) for nm in store.getNodeMemos())
    for n in ids:
        store.getSimpleNodeIdent(NodeID(n))  # ask for SNIP
    time.sleep(3)
    rows = []
    for n in ids:
        ident = store.getSimpleNodeIdent(NodeID(n))
        rows.append((n, ident.getModelName() or "", ident.getUserName() or ""))
    return rows


def find_cs105(rows):
    for n, model, _ in rows:
        if "CS-105" in model:
            return n
    return None


def run():
    memo = jmri.InstanceManager.getNullableDefault(jmri.jmrix.can.CanSystemConnectionMemo)
    iface = memo.get(OlcbInterface) if memo is not None else None
    if iface is None:
        raise RuntimeError("no OpenLCB/LCC connection in this JMRI")
    store = iface.getNodeStore()
    before = _nodes(store)
    cs105 = find_cs105(before)
    if cs105 is None:
        raise RuntimeError("no CS-105 on the bus")
    lines = ["rebooting CS-105 %s" % cs105]
    status = {"v": "no reply (expected)"}

    class _Memo(DatagramService.DatagramServiceTransmitMemo):
        def handleSuccess(self, flags):
            status["v"] = "acknowledged"

        def handleFailure(self, code):
            status["v"] = "rejected 0x%04X" % code

    iface.getDatagramService().sendData(_Memo(NodeID(cs105), [0x20, 0xA9]))
    time.sleep(3)
    lines.append("reboot datagram: %s" % status["v"])
    time.sleep(REBOOT_WAIT)
    store.refresh()
    time.sleep(REFRESH_WAIT)
    after = _nodes(store)
    gone = sorted(set(r[0] for r in before) - set(r[0] for r in after))
    lines.append("nodes after restart:")
    for n, model, name in after:
        lines.append("  %s | %s | %s" % (n, model, name))
    if gone:
        lines.append("gone since before the restart: " + ", ".join(gone))
    return "\n".join(lines)


RESULT = run()
