import time, threading, os, java, jmri
f=open(LOGF,"a")
def L(m): f.write("%.3f %s\n"%(time.time(),m)); f.flush()
class TL(jmri.ThrottleListener):
    def __init__(self): self.t=None; self.ev=threading.Event(); self.err=None
    def notifyThrottleFound(self,t): self.t=t; self.ev.set()
    def notifyFailedThrottleRequest(self,a,r): self.err="fail %s"%r; self.ev.set()
    def notifyDecisionRequired(self,a,d): self.err="decision %s"%d; self.ev.set()
    def notifyStealThrottleRequired(self,a): self.err="steal"; self.ev.set()
reg=[]; last=[time.time()]; mid=[False]; lastref=[0]; ref=[0]; ab=threading.Event(); why=[""]
class SL(java.beans.PropertyChangeListener):
    def __init__(self,n): self.n=n
    def propertyChange(self,e):
        if e.getPropertyName()!="KnownState": return
        st=e.getNewValue(); L("SENS %s %s"%(self.n,"ACTIVE" if st==2 else "INACTIVE")); last[0]=time.time()
        if self.n=="BS Switch 23a" and st==2: mid[0]=True
        if self.n in GUARD and st==2: why[0]="guard "+self.n; ab.set()
        if self.n==REF and st==2:
            if mid[0]: ref[0]+=1; mid[0]=False; lastref[0]=time.time(); L("REF %d"%ref[0])
            else: L("REF ignored (no mid-loop pass)")
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
        t=tl.t; t.setIsForward(True)
        for fn in FUNCS: getattr(t,"setF%d"%fn)(True)
        time.sleep(1.0)
        stall=STALL0
        for st in STEPS_LIST:
            nl=(LAPS_LOW if st<=16 else LAPS); t.setSpeedSetting(st/126.0); base=ref[0]; t0=time.time(); last[0]=t0
            L("STEP %d"%st)
            while ref[0]-base<nl+1:
                if ab.is_set(): return
                if os.path.exists("/tmp/speedrun.kill"): why[0]="killed"; return
                if time.time()-last[0]>stall: why[0]="stall %ds at step %d"%(stall,st); return
                time.sleep(0.1)
            lapt=(time.time()-t0)/float(nl+1)
            stall=max(90.0,3*lapt); L("STEPDONE %d avg_lap=%.1f"%(st,lapt))
        why[0]="all steps complete"
    except Exception, e: L("ERROR %s"%e)
    finally:
        L("STOP "+why[0])
        if t is not None: t.setSpeedSetting(0.0); L("speed 0")
        for s,l in reg: s.removePropertyChangeListener(l)
        L("END")
th=threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT="started"
