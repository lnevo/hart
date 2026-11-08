import time, threading, os, java, jmri
f=open(LOGF,"a")
def L(m): f.write("%.3f %s\n"%(time.time(),m)); f.flush()
class TL(jmri.ThrottleListener):
    def __init__(self): self.t=None; self.ev=threading.Event(); self.err=None
    def notifyThrottleFound(self,t): self.t=t; self.ev.set()
    def notifyFailedThrottleRequest(self,a,r): self.err="fail %s"%r; self.ev.set()
    def notifyDecisionRequired(self,a,d): self.err="decision %s"%d; self.ev.set()
    def notifyStealThrottleRequired(self,a): self.err="steal"; self.ev.set()
reg=[]; why=[""]; ab=threading.Event()
class SL(java.beans.PropertyChangeListener):
    def __init__(self,n): self.n=n
    def propertyChange(self,e):
        if e.getPropertyName()!="KnownState": return
        st=e.getNewValue(); L("SENS %s %s"%(self.n,"ACTIVE" if st==2 else "INACTIVE"))
        if self.n in GUARD and st==2: why[0]="guard "+self.n; ab.set()
def occ(sm,n): return sm.getSensor(n).getKnownState()==2
def run():
    t=None
    try:
        sm=jmri.InstanceManager.sensorManagerInstance()
        for s in sm.getNamedBeanSet():
            un=s.getUserName() or ""
            if un.startswith("BS ") and un not in ("BS W-1","BS W-2"):
                l=SL(un); s.addPropertyChangeListener(l); reg.append((s,l))
        re=jmri.jmrit.roster.Roster.getDefault().getEntryForId(P_ID)
        tl=TL(); jmri.InstanceManager.throttleManagerInstance().requestThrottle(re,tl,False); tl.ev.wait(10)
        if tl.t is None: L("NO THROTTLE %s"%tl.err); return
        t=tl.t; t.setIsForward(P_FWD); t.setF0(True)
        if P_ID=="CSX 2121": t.setF8(True)
        time.sleep(1.0)
        t.setSpeedSetting(P_STEP/126.0); L("GO %s step %d"%(P_ID,P_STEP)); t0=time.time()
        ok=0
        while not ab.is_set() and time.time()-t0<90:
            if os.path.exists("/tmp/speedrun.kill"): why[0]="killed"; break
            if eval(P_COND):
                ok+=1
                if ok>=8: why[0]=P_WHY; break
            else: ok=0
            time.sleep(0.1)
        if not why[0]: why[0]="time"
    except Exception, e: L("ERROR %s"%e)
    finally:
        L("STOP "+why[0])
        if t is not None: t.setSpeedSetting(0.0); L("speed 0")
        for s,l in reg: s.removePropertyChangeListener(l)
        L("END")
th=threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT="started"
