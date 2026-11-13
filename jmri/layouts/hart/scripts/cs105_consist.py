# cs105_consist.py - query, attach or detach an LCC consist on the TCS CS-105.
#
# Runs inside the Pi's JMRI (Jython 2.7), the host that owns the LCC link, normally
# dropped through jmri_cmd_watcher.py with its settings prepended:
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
# detach removes the listener on both nodes (each lists the other) and queries both.
# Train node of a long DCC address: 06.01.00.00.(C0|hi).lo (CSX 2121 = C8.49,
# CSX 2738 = CA.B2). Bytes above 127 must be sent as signed values (Jython).
# Never touches track power, turnouts or throttles.
# LCC consist helper (runs in the Pi's JMRI). ACTION = "query" | "attach" | "detach"
# NODES: list of train node ids to query; for attach/detach: LEAD, FOLLOW, FLAGS
import time, threading, jarray, jmri, java
from org.openlcb import NodeID, MessageDecoder, OlcbInterface
from org.openlcb.messages import TractionControlRequestMessage as Req
f=open(LOGF,"w")
def L(m): f.write("%s\n"%m); f.flush()
memo=jmri.InstanceManager.getNullableDefault(jmri.jmrix.can.CanSystemConnectionMemo)
iface=memo.get(OlcbInterface)
replies=[]
class H(MessageDecoder):
    def handleTractionControlReply(self, msg, sender):
        try:
            if msg.getCmd()==0x30: replies.append((str(msg.getSourceNodeID()), msg))
        except Exception, e: pass
h=H(); iface.registerMessageListener(h)
def send(dst, data):
    iface.getOutputConnection().put(Req(iface.getNodeId(), NodeID(dst), jarray.array([(x if x<128 else x-256) for x in data],'b')), None)
def detach_or_attach(sub, flags, node):
    # Listener attach (0x01) and detach (0x02) are 9 bytes: 0x30, sub, flags, then the
    # 6-byte node id (OpenLCB TractionControlRequestMessage.createConsistAttach/Detach).
    # Without the flags byte the CS-105 reads the wrong node and changes nothing.
    return [0x30, sub, flags] + [int(x,16) for x in node.split(".")]
def query(node):
    del replies[:]
    send(node,[0x30,0x03]); time.sleep(1.5)
    n=None
    for src,m in list(replies):
        if src.upper()==node.upper():
            try: n=m.getConsistLength()
            except Exception: pass
    L("%s listeners: %s"%(node,n))
    if not n: return
    for i in range(n):
        del replies[:]
        send(node,[0x30,0x03,i]); time.sleep(1.2)
        for src,m in list(replies):
            if src.upper()==node.upper():
                try:
                    p=[(x+256)%256 for x in m.getPayload()]
                    L("  raw payload: %s"%" ".join("%02X"%x for x in p))
                    # reply layout: 30 03 count index flags node(6)
                    L("  [%d] flags 0x%02X node %s"%(p[3], p[4], ".".join("%02X"%x for x in p[5:11])))
                except Exception, e: L("  [%d] decode error %s"%(i,e))
def run():
    try:
        if ACTION=="query":
            for n in NODES: query(n)
        elif ACTION in ("attach","detach"):
            if ACTION=="attach":
                send(LEAD,detach_or_attach(0x01,FLAGS,FOLLOW))
                L("attach %s on %s flags 0x%02X"%(FOLLOW,LEAD,FLAGS)); time.sleep(2)
            else:
                # each side lists the other, so drop the listener on both
                for a,b in ((LEAD,FOLLOW),(FOLLOW,LEAD)):
                    send(a,detach_or_attach(0x02,0,b))
                    L("detach %s on %s"%(b,a)); time.sleep(2)
            for n in (LEAD,FOLLOW): query(n)
    except Exception, e: L("ERROR %s"%e)
    except java.lang.Throwable, e: L("ERROR %s"%e)
    finally:
        iface.unRegisterMessageListener(h); L("END")
t=threading.Thread(target=run); t.setDaemon(True); t.start()
RESULT="started"
