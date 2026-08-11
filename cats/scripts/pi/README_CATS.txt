HART Digicon (CATS) on this Pi
==============================

Installed:
  /home/pi/JMRI/cats.jar          CATS 3.2 + MQTT load-safety overlay
  /home/pi/JMRI/designer.jar
  /home/pi/JMRI/cats.csh
  /home/pi/hart/cats/panels/sheets/HART_Master.xml            <-- primary CTC Digicon
  /home/pi/hart/cats/panels/sheets/HART_Master_ABS.xml        <-- ABS / open house
  /home/pi/hart/cats/panels/sheets/HART_Master_ABS_hold.xml   <-- ABS-RO (signals hold; turnouts on)

Launch (after quitting PanelPro):
  /home/pi/hart/launch_cats.sh
  # default panel = HART_Master.xml

Desktop icons:
  CATS         -> HART_Master.xml            (/home/pi/hart/launch_hart_master_desktop.sh)
  CATS ABS     -> HART_Master_ABS.xml        (/home/pi/hart/launch_hart_master_abs_desktop.sh)
  CATS ABS-RO  -> HART_Master_ABS_hold.xml   (/home/pi/hart/launch_hart_master_abs_hold_desktop.sh)

Or with an explicit panel:
  /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/sheets/HART_Master.xml
  /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/sheets/HART_Master_ABS.xml
  /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/sheets/HART_Master_ABS_hold.xml

Profile used: TCS_MQTT.3f32a166 (same as current PanelPro)

JMRI tables (routes, internal turnouts, etc.):
  Startup loads preference:tables.xml
  On this Pi, preference: → /home/pi/JMRI_UserFiles/  (NOT the profile folder)
  Live file: /home/pi/JMRI_UserFiles/tables.xml
  Repo mirror: jmri/layouts/hart/output/pi_tables.xml
  Yard-ladder buttons need IO:AUTO:0201–0210 + IT:HART:YL:* in that file.
  Do not patch only ~/.jmri/TCS_MQTT.jmri/tables.xml — CATS will ignore it.

Do NOT run PanelPro and CATS at the same time on this profile.
Use one Digicon as signal authority (CATS or CATS ABS).
CATS ABS-RO still throws turnouts / shows occupancy; signals are HOLD_ONLY
(paints from MQTT — does not drive Clear/Approach/Stop).

TrainStat (optional yard/trainmaster client)
============================================

Installed:
  /home/pi/hart/trainstat/              TrainStat package
  /home/pi/hart/trainstat/hart_trainstat.xml   connects to localhost:54321

Launch (CATS must already be running):
  /home/pi/hart/launch_trainstat.sh
  # or desktop icon: TrainStat

In CATS: Network menu should show Start TrainStat Server checked
(panel includes <TRAINSTATLABEL /> which enables it on load).
