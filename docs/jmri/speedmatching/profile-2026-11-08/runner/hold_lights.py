import time, threading, os, jmri
LOG="/tmp/lights.log"
class TL(jmri.ThrottleListener):
    def __init__(self): self.t=None; self.ev=threading.Event(); self.err=None
    def notifyThrottleFound(self,t): self.t=t; self.ev.set()
    def notifyFailedThrottleRequest(self,a,r): self.err="fail %s"%r; self.ev.set()
    def notifyDecisionRequired(self,a,d): self.err="decision %s"%d; self.ev.set()
    def notifyStealThrottleRequired(self,a): self.err="steal"; self.ev.set()
def run():
    f=open(LOG,"w")
    re=jmri.jmrit.roster.Roster.getDefault().getEntryForId("CR 1993")
    tl=TL(); jmri.InstanceManager.throttleManagerInstance().requestThrottle(re,tl,False); tl.ev.wait(10)
    if tl.t is None: f.write("NO THROTTLE %s\n"%tl.err); f.close(); return
    t=tl.t; t.setSpeedSetting(0.0); t.setF0(True); f.write("CR 1993 F0 on, speed 0, holding\n"); f.flush()
    while not os.path.exists("/tmp/lights.kill"): time.sleep(1)
    t.setF0(False); f.write("released\n"); f.close()
th=threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT="started"
